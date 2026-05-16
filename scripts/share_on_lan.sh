#!/usr/bin/env bash
# Temporarily allow LAN access to the Vite dev server, then undo on exit.
# Start the stack first (backend on 0.0.0.0:8000, web: npm run dev -- --host 0.0.0.0 --port 5173).
#
# Optional when there is no firewalld/ufw:
#   FMR_USE_IPTABLES=1   — prefers iptables-legacy (often works when iptables shim errors)
#   FMR_USE_NFT=1        — inserts into inet filter input via nft only (needs that chain/table)

set -euo pipefail

PORTS=(5173)
FIREWALL="none"
IPTABLES_CMD=""
NFT_HANDLE_FILE=""

# Try legacy first: default `iptables` on many systems is an nf_tables shim and can fail with
# "Could not fetch rule set generation id" / missing tcp revision.
pick_iptables() {
  local c
  for c in iptables-legacy iptables-nft iptables; do
    command -v "$c" >/dev/null 2>&1 || continue
    if sudo "${c}" -t filter -S INPUT >/dev/null 2>&1; then
      echo "${c}"
      return 0
    fi
  done
  return 1
}

nft_chain_exists() {
  command -v nft >/dev/null 2>&1 && nft list chain inet filter input >/dev/null 2>&1
}

# After insert with comment containing tag="$1", print numeric nft handle id for deletion (handles indented nft output).
nft_handle_for_comment_tag() {
  local tag="$1"
  sudo nft -a list chain inet filter input |
    python3 -c '
import re, sys
tag = sys.argv[1]
lines = sys.stdin.read().splitlines()
nl = chr(10)
for i, ln in enumerate(lines):
    if tag not in ln:
        continue
    chunk = nl.join(lines[i : i + 12])
    m = re.search(r"#\s*handle\s+(\d+)", chunk)
    if m:
        print(m.group(1))
        sys.exit(0)
sys.exit(1)
' "${tag}"
}

detect_firewall() {
  if [[ "${FMR_USE_NFT:-}" == "1" ]]; then
    if ! nft_chain_exists; then
      echo "FMR_USE_NFT=1 needs an existing chain: inet filter input" >&2
      echo "Check: nft list chain inet filter input || sudo nft list ruleset | head -50" >&2
      exit 1
    fi
    FIREWALL=nft
  elif [[ "${FMR_USE_IPTABLES:-}" == "1" ]]; then
    if IPTABLES_CMD="$(pick_iptables)"; then
      FIREWALL=iptables
    else
      echo "iptables did not respond (iptables vs kernel nf_tables mismatch is common on Arch)." >&2
      echo "Try pure nft instead: FMR_USE_NFT=1 $0" >&2
      exit 1
    fi
  elif systemctl is-active --quiet firewalld 2>/dev/null; then
    FIREWALL=firewalld
  elif command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -qiE '^Status:\s+active'; then
    FIREWALL=ufw
  else
    FIREWALL=none
  fi
}

lan_ip() {
  local ip
  ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}')
  if [[ -n "${ip}" ]]; then
    echo "${ip}"
    return
  fi
  hostname -I 2>/dev/null | awk '{ print $1; exit }'
}

# Warn if nothing is bound for LAN (0.0.0.0, *, or [::]) on 5173 — common LAN sharing failure.
check_vite_bind() {
  local lines
  if ! command -v ss >/dev/null 2>&1; then
    return 0
  fi
  lines=$(ss -H -tln 2>/dev/null | grep -E ':5173([[:space:]]|$)' || true)
  [[ -z "${lines}" ]] && return 0
  if echo "${lines}" | grep -qE '(^|[[:space:]])(\*|0\.0\.0\.0):5173\b'; then
    return 0
  fi
  if echo "${lines}" | grep -qF '[::]:5173'; then
    return 0
  fi
  echo "WARNING: port 5173 is not listening on all interfaces — other LAN devices usually cannot connect." >&2
  echo "Fix: npm run dev -- --host 0.0.0.0 --port 5173" >&2
}

open_ports() {
  local p
  case "${FIREWALL}" in
    firewalld)
      for p in "${PORTS[@]}"; do
        sudo firewall-cmd --add-port="${p}/tcp" --quiet
      done
      ;;
    ufw)
      for p in "${PORTS[@]}"; do
        sudo ufw allow "${p}/tcp" comment 'find-my-race-temp'
      done
      ;;
    iptables)
      for p in "${PORTS[@]}"; do
        if ! sudo "${IPTABLES_CMD}" -I INPUT 1 -p tcp --dport "${p}" -j ACCEPT; then
          echo "iptables -I failed; try FMR_USE_NFT=1 $0" >&2
          exit 1
        fi
      done
      ;;
    nft)
      NFT_HANDLE_FILE=$(mktemp)
      for p in "${PORTS[@]}"; do
        tag="fmr$$-${p}"
        if ! sudo nft insert rule inet filter input position 0 tcp dport "${p}" accept comment \""${tag}"\"; then
          echo "nft insert failed for port ${p}." >&2
          exit 1
        fi
        if ! h=$(nft_handle_for_comment_tag "${tag}"); then
          echo "Could not read nft handle for comment tag ${tag}; remove the rule manually: sudo nft list chain inet filter input -a" >&2
          exit 1
        fi
        echo "${h}" >>"${NFT_HANDLE_FILE}"
      done
      ;;
    none)
      echo "No active firewalld or ufw found; skipping firewall changes." >&2
      echo "If this machine uses iptables/nft without a manager, try:" >&2
      echo "  FMR_USE_IPTABLES=1 $0   # tries iptables-legacy first" >&2
      echo "  FMR_USE_NFT=1 $0        # if you have table inet filter / chain input" >&2
      ;;
  esac
}

close_ports() {
  local p
  case "${FIREWALL}" in
    firewalld)
      for p in "${PORTS[@]}"; do
        sudo firewall-cmd --remove-port="${p}/tcp" --quiet 2>/dev/null || true
      done
      ;;
    ufw)
      for p in "${PORTS[@]}"; do
        sudo ufw delete allow "${p}/tcp" >/dev/null 2>&1 || true
      done
      ;;
    iptables)
      for p in "${PORTS[@]}"; do
        sudo "${IPTABLES_CMD}" -D INPUT -p tcp --dport "${p}" -j ACCEPT 2>/dev/null || true
      done
      ;;
    nft)
      if [[ -n "${NFT_HANDLE_FILE}" ]] && [[ -f "${NFT_HANDLE_FILE}" ]]; then
        while read -r h; do
          [[ -z "${h}" ]] && continue
          sudo nft delete rule inet filter input handle "${h}" 2>/dev/null || true
        done <"${NFT_HANDLE_FILE}"
        rm -f "${NFT_HANDLE_FILE}"
      fi
      ;;
  esac
}

cleanup() {
  trap - EXIT INT TERM
  if [[ "${FIREWALL}" != "none" ]]; then
    echo ""
    echo "Removing temporary firewall rules for ports: ${PORTS[*]}"
    close_ports
  fi
}

trap 'cleanup' EXIT INT TERM

detect_firewall
if [[ "${FIREWALL}" == "iptables" ]]; then
  echo "Firewall backend: iptables (${IPTABLES_CMD})"
else
  echo "Firewall backend: ${FIREWALL}"
fi
echo "Opening TCP ports: ${PORTS[*]}"
open_ports
check_vite_bind

IP="$(lan_ip || true)"
if [[ -z "${IP}" ]]; then
  echo "Could not detect LAN IP; use your machine's Wi‑Fi/Ethernet address manually." >&2
else
  echo ""
  echo "On another device on the same network, open:"
  echo "  http://${IP}:5173"
  echo ""
  echo "This host must be running:"
  echo "  backend: uvicorn app.main:app --host 0.0.0.0 --port 8000"
  echo "  web:     npm run dev -- --host 0.0.0.0 --port 5173"
fi

echo ""
echo "Press Enter to close firewall exposure and exit (Ctrl+C does the same)…"
read -r _

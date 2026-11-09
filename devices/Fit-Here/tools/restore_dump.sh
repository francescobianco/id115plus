#!/usr/bin/env bash
# Decifra il dump della flash in devices/Fit-Here/dump/ e ne verifica l'hash.
# La password la chiede gpg. Non sovrascrive mai un dump/ esistente.
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE="$BASE/dump-2026-11-09.tar.gz.gpg"
DUMP="$BASE/dump"
EXPECTED="dc30a2e7619591e8bb42a365af6c3cc7f40a24f2f518adb669c0a8452ef4794f"

hash_of() { sha256sum "$1" | cut -d' ' -f1; }
die() { echo "ERRORE: $*" >&2; exit 1; }

if [[ -f "$DUMP/flash.final.bin" ]]; then
    [[ "$(hash_of "$DUMP/flash.final.bin")" == "$EXPECTED" ]] \
        || die "$DUMP/flash.final.bin esiste ma l'hash non coincide: controllalo a mano."
    echo "Dump già presente e verificato: $DUMP/flash.final.bin"
    exit 0
fi

[[ -f "$ARCHIVE" ]] || die "archivio non trovato: $ARCHIVE"
if [[ -d "$DUMP" && -n "$(ls -A "$DUMP")" ]]; then
    die "$DUMP contiene già dei file ma non flash.final.bin: controllalo a mano."
fi

TMP="$(mktemp -d "$BASE/.dump-restore.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

gpg -d "$ARCHIVE" | tar xzf - -C "$TMP" || die "decifratura o estrazione fallita (password sbagliata?)."

[[ -f "$TMP/flash.final.bin" ]] || die "flash.final.bin non è nell'archivio."
ACTUAL="$(hash_of "$TMP/flash.final.bin")"
[[ "$ACTUAL" == "$EXPECTED" ]] || die "hash errato: $ACTUAL"

[[ -d "$DUMP" ]] && rmdir "$DUMP"
chmod 755 "$TMP"
mv "$TMP" "$DUMP"
trap - EXIT

echo "Dump ripristinato e verificato: $DUMP/flash.final.bin"
echo "SHA-256: $ACTUAL"

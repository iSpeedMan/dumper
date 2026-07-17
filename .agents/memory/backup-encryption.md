---
name: Backup file encryption
description: Config backups stored as AES-256-GCM encrypted blobs (config.enc) in git repo; plain text never written to disk.
---

# Backup File Encryption

## Rule
`app/git_manager.py` always encrypts config content before writing to disk and decrypts after reading. The file is named `config.enc` (not `config.txt`).

## Format
Binary blob: `b"DUMPER_ENC_V1\n" + base64(nonce[12] + ciphertext + tag[16])`

The `DUMPER_ENC_V1\n` prefix distinguishes encrypted blobs from legacy plain-text files.

## Migration
`get_latest_config()` falls back to reading `config.txt` (plain text) if `config.enc` doesn't exist — allows gradual migration of pre-existing repos.

## Why
Ensures configs are unreadable directly from the filesystem even with full disk access. Only the app (which holds the master key) can decrypt them.

## How to apply
- `save_and_commit`: encrypts before write, computes diff in-memory from decrypted content
- `get_diff_between_commits`: decrypts both blobs before diffing
- `get_config_at_commit`: decrypts before returning
- `get_latest_config`: decrypts config.enc; falls back to config.txt

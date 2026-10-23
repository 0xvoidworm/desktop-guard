# AGENTS.md — desktop-guard

Guard aturan desktop Windows: hanya **This PC**, **Terminal**, dan **wormGPT**
yang boleh tampil. Ikon lain disembunyikan **di tempat** (atribut Hidden).

## Kontrak proyek

- Bahasa: Python (stdlib saja, tanpa dependency runtime).
- File utama: `desktop_guard.py`; aturan per-shorcut di `config.json`.
- Prinsip: **tidak** menghapus file, **tidak** mencopot aplikasi, **tidak**
  menyentuh jaringan.
- Loop polling tiap 1 detik pada Desktop pribadi + Public Desktop.

## Perintah

```bash
python3 -m py_compile desktop_guard.py        # cek sintaks
python3 test_desktop_guard.py                 # test (bisa jalan di Linux?)
python3 desktop_guard.py                      # jalankan (Windows)
```

## Aturan main

- Jangan menambah dependensi eksternal tanpa alasan terukur.
- Jangan mengubah `config.json` untuk menambah/menghapus shortcut tanpa
  instruksi operator.
- Jangan pernah membaca atau mencetak kredensial/path profil pengguna.

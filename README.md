```text
╭───────────────────────────────────────────────────────────────╮
│   d e s k t o p - g u a r d                                   │
│   [INFRA] the desktop, on a short leash · sejak 11 Sep 2026    │
╰───────────────────────────────────────────────────────────────╯
```

> Desktop Windows yang taat aturan: hanya **This PC**, **Terminal**, dan
> **wormGPT** yang tampil. Ikon lain disembunyikan di tempat — tidak ada file
> dihapus, tidak ada aplikasi dicopot, tidak ada akses jaringan.

## Kenapa

Membuka desktop dan melihat belasan ikon membuat kerja susah dimulai. Aturan
proyek ini cuma satu: yang boleh tampil hanya tiga shortcut itu, sisanya diberi
atribut **Hidden** di tempat.

## Cara kerja

- Memantau tingkat teratas Desktop pribadi dan Public Desktop setiap 1 detik,
  tanpa memindai isi subfolder.
- Tiga nama shortcut di `config.json` dibiarkan utuh; penjaga tidak menjalankan
  atau mengubah target shortcut.
- Item lain diberi atribut **Hidden** di tempat — isi dan lokasinya tetap sama.
- Kalau izin Public Desktop menolak, hanya shortcut `.lnk`/`.url` yang stabil
  minimal 2 detik yang dipindahkan secara recoverable ke
  `outputs/desktop-guard/PublicDesktop` (nama unik, tidak menimpa, hash
  diverifikasi).
- Tidak menghapus file, mencopot aplikasi, mengubah ACL, memakai hak
  administrator, atau mengakses jaringan.
- Log lokal dirotasi sekitar 3 MB; status proses ditulis ke
  `outputs/desktop-guard/status.json`.

## Pakai

```powershell
pythonw desktop_guard.py     # jalankan
New-Item STOP                # hentikan (proses keluar ~1 detik)
```

- Dependensi: Python standard library saja — tidak memasang paket apa pun.
- Startup otomatis per pengguna: taruh shortcut `Desktop Guard.lnk` di
  `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`.
- Mengubah daftar yang diizinkan: edit `config.json`, lalu jalankan ulang
  penjaga (konfigurasi dibaca saat proses mulai).
- Penjaga tidak otomatis menampilkan kembali item yang sudah disembunyikan
  setelah dihentikan; atribut sebelumnya tercatat di log untuk pemulihan.

## Verifikasi

- Lima unit test lolos: pelestarian tiga shortcut, atribut hanya di tingkat
  teratas, fallback shortcut publik, item yang aksesnya ditolak tidak
  dipaksa, dan pemindaian berulang yang aman.
- Tes nyata: shortcut dan folder uji otomatis menjadi Hidden dalam jendela
  pengujian 3 detik; hash tiga shortcut utama tidak berubah; bukti disimpan di
  `outputs/desktop-guard/test-evidence`.
- Kunci instance mencegah proses kedua berjalan ganda.

## Batasan

- Bersifat reaktif, bukan pencegahan: item bisa terlihat sekilas sebelum
  pemindaian berikutnya; fallback Public Desktop butuh beberapa detik.
- Menyalakan "Show hidden items" membuat item tersembunyi terlihat lagi —
  preferensi ini sengaja tidak diubah.
- Public Desktop milik bersama: pemindahannya berdampak ke akun lain di laptop
  yang sama.
- Izin yang menolak perubahan atribut/pemindahan, reparse point/junction,
  namespace baru yang belum terdaftar, atau runtime Python yang dihapus akan
  membatasi penegakan aturan.

## Lisensi

MIT — lihat [LICENSE](LICENSE).

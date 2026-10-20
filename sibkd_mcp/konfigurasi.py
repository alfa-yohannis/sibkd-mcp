"""Konfigurasi: kredensial, setelan, sesi HTTP, dan penyimpanan hasil.

Paket ini dipakai dari dua arah, dan keduanya harus benar tanpa disetel apa pun:

    berdiri sendiri   repositori ini di-clone lalu dijalankan lewat ./sibkd.
                      Akar proyek = direktori repositori itu sendiri.

    sebagai pustaka   proyek lain memasangnya (`pip install sibkd-mcp`) dan
                      mengimpor `sibkd_mcp`. Akar proyek = direktori kerja
                      proyek itu, bukan site-packages tempat paket ini terpasang.

Akar proyek menentukan letak berkas-berkas ini:

    <akar>/.env          kredensial (SIBKD_USERNAME, SIBKD_PASSWORD)
    <akar>/sibkd.yaml    setelan non-rahasia (alamat instance, path, batas waktu)
    <akar>/data/         hasil tarikan dan berkas yang diunduh

Direktori di atasnya tidak pernah ikut ditelusuri, supaya hasilnya tidak berubah
hanya karena paket ini dipindah. Proyek yang memakainya sebagai pustaka bisa
menentukan sendiri lewat `atur_akar_proyek()` atau `atur_setelan()`, atau lewat
SIBKD_AKAR_PROYEK.

Rahasia dipisah dari setelan dengan sengaja: `.env` memuat username/password dan
tidak pernah ikut ter-commit, sedangkan `sibkd.yaml` aman dibagikan.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from dotenv import dotenv_values

PENYAMARAN_BROWSER = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class KonfigurasiError(RuntimeError):
    """Setelan atau kredensial yang tidak bisa dipakai.

    Sengaja bukan SystemExit: pustaka tidak boleh menghentikan program yang
    memakainya. Titik masuk CLI yang menangkap ini dan keluar dengan rapi.
    """


# Ditetapkan dari kode lewat atur_akar_proyek()/atur_setelan(); dipakai proyek
# lain yang tidak mau bergantung pada berkas atau environment sama sekali.
_akar_ditetapkan: Path | None = None
_setelan_ditetapkan: dict[str, str] = {}
_konfigurasi_tersimpan: dict | None = None


def akar_bawaan() -> Path:
    """Akar proyek kalau tidak ada yang menentukan.

    Kalau paket ini berada di dalam checkout repositorinya sendiri, direktori
    repositori itulah akarnya (mode "berdiri sendiri"). Kalau sudah terpasang
    sebagai pustaka, site-packages jelas bukan tempat menaruh .env milik
    pemakai, jadi yang dipakai direktori kerja proyek pemanggil.
    """
    akar_repo = Path(__file__).resolve().parent.parent
    if (akar_repo / "pyproject.toml").is_file():
        return akar_repo
    return Path.cwd()


def akar_proyek() -> Path:
    """Direktori tempat .env, sibkd.yaml, dan data/ dicari."""
    if _akar_ditetapkan is not None:
        return _akar_ditetapkan
    ditetapkan = os.environ.get("SIBKD_AKAR_PROYEK") or os.environ.get("BKD_AKAR_PROYEK")
    if ditetapkan:
        return Path(ditetapkan).expanduser()
    return akar_bawaan()


def atur_akar_proyek(path: str | Path | None) -> None:
    """Tetapkan akar proyek dari kode. `None` mengembalikan ke perilaku bawaan."""
    global _akar_ditetapkan
    _akar_ditetapkan = Path(path).expanduser().resolve() if path is not None else None
    lupakan_konfigurasi()


def atur_setelan(**nilai: object) -> None:
    """Setelan dari kode, mis. `atur_setelan(base_url="https://sibkd.lain.go.id")`.

    Kuncinya boleh gaya YAML (`base_url`) atau gaya environment
    (`SIBKD_BASE_URL`). Ini kepastian tertinggi: proyek yang menyetel sesuatu
    secara eksplisit tidak boleh berubah diam-diam karena environment mesin.
    Panggil tanpa argumen untuk mengosongkannya kembali.
    """
    if not nilai:
        _setelan_ditetapkan.clear()
        return
    for kunci, isi in nilai.items():
        _setelan_ditetapkan[nama_di_yaml(kunci)] = str(isi)


def lupakan_konfigurasi() -> None:
    """Buang isi sibkd.yaml yang diingat, supaya dibaca ulang berikutnya."""
    global _konfigurasi_tersimpan
    _konfigurasi_tersimpan = None


def berkas_env() -> Path:
    """Letak .env yang dipakai."""
    return akar_proyek() / ".env"


def dir_data() -> Path:
    """Direktori hasil tarikan."""
    return akar_proyek() / "data"


def path_dari_akar(path: str | Path) -> Path:
    """Path relatif dihitung dari akar proyek; path absolut dipakai apa adanya."""
    lokasi = Path(path).expanduser()
    return lokasi if lokasi.is_absolute() else akar_proyek() / lokasi


def path_masukan(path: str | Path) -> Path:
    """Letak berkas masukan (mis. PDF yang akan diunggah).

    Path relatif dicari dulu dari direktori kerja, seperti kebiasaan perintah
    terminal, lalu dari akar proyek, tempat asisten AI biasanya menaruh berkas.
    """
    lokasi = Path(path).expanduser()
    if lokasi.is_absolute() or lokasi.exists():
        return lokasi.resolve()
    return akar_proyek() / lokasi


def berkas_konfigurasi() -> Path | None:
    """Berkas sibkd.yaml (atau .yml) yang dipakai, kalau memang ada."""
    akar = akar_proyek()
    for nama in ("sibkd.yaml", "sibkd.yml"):
        if (akar / nama).is_file():
            return akar / nama
    return None


def muat_konfigurasi() -> dict:
    """Isi sibkd.yaml sebagai dict datar. Dibaca sekali lalu diingat.

    PyYAML sengaja diimpor di sini, bukan di kepala modul: pemakai yang cukup
    dengan setelan bawaan tidak perlu punya berkas konfigurasi sama sekali.
    """
    global _konfigurasi_tersimpan
    if _konfigurasi_tersimpan is not None:
        return _konfigurasi_tersimpan

    berkas = berkas_konfigurasi()
    if berkas is None:
        _konfigurasi_tersimpan = {}
        return _konfigurasi_tersimpan

    try:
        import yaml
    except ImportError as galat:
        raise KonfigurasiError(
            f"{berkas} ada tapi PyYAML belum terpasang. Pasang dulu: pip install pyyaml"
        ) from galat

    isi = yaml.safe_load(berkas.read_text(encoding="utf-8")) or {}
    if not isinstance(isi, dict):
        raise KonfigurasiError(
            f"{berkas} harus berupa pemetaan kunci: nilai, bukan {type(isi).__name__}"
        )
    _konfigurasi_tersimpan = isi
    return _konfigurasi_tersimpan


def nama_di_yaml(kunci: str) -> str:
    """SIBKD_BASE_URL -> base_url; kunci tanpa awalan dipakai apa adanya."""
    return kunci[len("SIBKD_"):].lower() if kunci.startswith("SIBKD_") else kunci.lower()


def baca_pengaturan(kunci: str, bawaan: str = "") -> str:
    """Setelan opsional, dari yang paling khusus ke yang paling umum:

        atur_setelan()  ->  environment  ->  .env  ->  sibkd.yaml  ->  bawaan

    Kuncinya ditulis gaya environment (SIBKD_BASE_URL); di sibkd.yaml nama yang
    sama dipakai tanpa awalan SIBKD_ dan huruf kecil (base_url).

    Berbeda dengan baca_kredensial() yang mewajibkan, ini dipakai untuk nilai
    yang boleh kosong, mis. alamat instance atau path halaman.
    """
    dari_kode = _setelan_ditetapkan.get(nama_di_yaml(kunci))
    if dari_kode:
        return dari_kode

    dari_lingkungan = os.environ.get(kunci) or dotenv_values(berkas_env()).get(kunci)
    if dari_lingkungan:
        return dari_lingkungan

    dari_berkas = muat_konfigurasi().get(nama_di_yaml(kunci))
    return str(dari_berkas) if dari_berkas not in (None, "") else bawaan


def baca_angka(kunci: str, bawaan: int) -> int:
    """Setelan berupa bilangan bulat; isian yang tidak masuk akal ditolak jelas."""
    nilai = baca_pengaturan(kunci, str(bawaan))
    try:
        return int(nilai)
    except ValueError as galat:
        raise KonfigurasiError(f"Setelan {kunci} harus berupa angka, bukan {nilai!r}") from galat


def baca_kredensial(*kunci_wajib: str) -> dict[str, str]:
    """Ambil kredensial yang diminta. Error kalau ada yang belum diisi.

    Sumbernya sama dengan setelan lain, jadi proyek yang memakai pustaka ini
    boleh memberikannya lewat atur_setelan() atau environment tanpa perlu
    menyediakan berkas .env sama sekali.
    """
    hasil = {kunci: baca_pengaturan(kunci) for kunci in kunci_wajib}
    belum_ada = [kunci for kunci, nilai in hasil.items() if not nilai]
    if belum_ada:
        raise KonfigurasiError(
            f"Kredensial belum ada: {', '.join(belum_ada)}. "
            f"Isi di {berkas_env()}, lewat environment, atau atur_setelan()."
        )
    return hasil


def buat_sesi_http() -> requests.Session:
    """Sesi yang menyimpan cookie, menyamar sebagai browser, dan memakai rantai TLS lengkap.

    Server SIBKD tidak mengirim sertifikat antaranya, jadi sesi biasa gagal
    memverifikasi; rantai_tls menambal mata rantai itu tanpa mematikan
    verifikasi. Diimpor di sini supaya tidak terjadi impor melingkar.
    """
    from sibkd_mcp.rantai_tls import pasang_rantai_tls

    sesi = requests.Session()
    sesi.headers.update({"User-Agent": baca_pengaturan("SIBKD_USER_AGENT", PENYAMARAN_BROWSER)})
    return pasang_rantai_tls(sesi)


def simpan_ke_data(nama_berkas: str, isi, *, teks_mentah: bool = False) -> Path:
    """Simpan hasil tarikan ke data/. JSON secara bawaan, teks mentah kalau diminta."""
    tujuan_dir = dir_data()
    tujuan_dir.mkdir(parents=True, exist_ok=True)
    tujuan = tujuan_dir / nama_berkas
    if teks_mentah:
        tujuan.write_text(isi, encoding="utf-8")
    else:
        tujuan.write_text(json.dumps(isi, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  tersimpan: {tujuan}")
    return tujuan

"""Rantai sertifikat TLS untuk SIBKD.

Server SIBKD hanya mengirim sertifikat daun (*.kemdiktisaintek.go.id, diterbitkan
"Sectigo Public Server Authentication CA DV R36") tanpa sertifikat antaranya.
Browser biasanya menambal kekurangan itu sendiri dari cache atau dengan
mengunduh penerbitnya; requests tidak, sehingga setiap permintaan gagal dengan
"unable to get local issuer certificate". Host lain di domain yang sama
(EL-KITE) mengirim rantai lengkap, jadi masalahnya ada di konfigurasi server
SIBKD.

Paket ini membawa dua sertifikat antara sebagai data paket
(sertifikat/sectigo_antara.pem):

    Sectigo Public Server Authentication CA DV R36   (diterbitkan R46)
    Sectigo Public Server Authentication Root R46    (ditandatangani silang
                                                      USERTrust RSA, yang ada
                                                      di bundel certifi)

Keduanya ditambahkan ke bundel certifi pada satu `ssl.SSLContext`, lalu konteks
itu dipasang ke sesi lewat adaptor HTTP. Verifikasi tetap penuh: nama host dan
rantai sampai akar tepercaya tetap diperiksa, yang ditambahkan hanya mata rantai
yang hilang. Tidak ada jalan untuk mematikannya.

Setelan SIBKD_CA_BUNDLE (atau `ca_bundle:` di sibkd.yaml) menggantikan semua itu
dengan bundel CA pilihan pemakai, mis. bundel sistem yang sudah ditambahi
sertifikat antara oleh administrator.
"""

from __future__ import annotations

import ssl
from importlib import resources
from pathlib import Path

import certifi
import requests
from requests.adapters import HTTPAdapter

from sibkd_mcp.konfigurasi import KonfigurasiError, baca_pengaturan, path_dari_akar

NAMA_PEM_ANTARA = "sectigo_antara.pem"


def pem_antara() -> str:
    """Isi PEM sertifikat antara yang dibawa paket ini."""
    return (resources.files("sibkd_mcp") / "sertifikat" / NAMA_PEM_ANTARA).read_text(encoding="ascii")


def berkas_ca_bundle() -> Path | None:
    """Bundel CA pengganti dari SIBKD_CA_BUNDLE, kalau diisi.

    Path relatif dihitung dari akar proyek. Path yang salah ditolak dengan pesan
    jelas: diam-diam jatuh ke bawaan akan menyembunyikan salah ketik.
    """
    nilai = baca_pengaturan("SIBKD_CA_BUNDLE")
    if not nilai:
        return None
    bundel = path_dari_akar(nilai)
    if not bundel.exists():
        raise KonfigurasiError(f"SIBKD_CA_BUNDLE menunjuk {bundel}, tapi berkasnya tidak ada")
    return bundel


def buat_konteks_tls() -> ssl.SSLContext:
    """Konteks TLS berverifikasi penuh yang mengenal sertifikat antara SIBKD."""
    bundel = berkas_ca_bundle()
    if bundel is not None:
        if bundel.is_dir():
            return ssl.create_default_context(capath=str(bundel))
        return ssl.create_default_context(cafile=str(bundel))

    konteks = ssl.create_default_context(cafile=certifi.where())
    konteks.load_verify_locations(cadata=pem_antara())
    return konteks


class AdaptorTls(HTTPAdapter):
    """HTTPAdapter yang memakai `ssl.SSLContext` buatan sendiri.

    requests tidak menyediakan parameter untuk konteks TLS, jadi konteksnya
    diselipkan saat pool koneksi dibuat. `konteks` harus sudah terpasang
    sebelum `super().__init__()`, karena di sanalah init_poolmanager dipanggil.
    """

    def __init__(self, konteks: ssl.SSLContext, **kwargs):
        self.konteks = konteks
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self.konteks
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        proxy_kwargs["ssl_context"] = self.konteks
        return super().proxy_manager_for(proxy, **proxy_kwargs)


def pasang_rantai_tls(sesi: requests.Session) -> requests.Session:
    """Pasang konteks TLS SIBKD ke semua permintaan https sesi ini.

    Kalau SIBKD_CA_BUNDLE diisi, `sesi.verify` ikut menunjuk bundel itu supaya
    requests tidak menambahkan bundel certifi bawaannya ke konteks.
    """
    bundel = berkas_ca_bundle()
    sesi.mount("https://", AdaptorTls(buat_konteks_tls()))
    if bundel is not None:
        sesi.verify = str(bundel)
    return sesi

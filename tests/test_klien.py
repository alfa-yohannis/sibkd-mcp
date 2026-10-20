"""Uji klien SIBKD tanpa jaringan: login, sesi habis, balasan JSON, unduhan, dan TLS."""

from __future__ import annotations

import ssl

import pytest
import requests

from conftest import BASE, HALAMAN_LOGIN, JawabanTiruan
from sibkd_mcp import konfigurasi
from sibkd_mcp.rantai_tls import AdaptorTls, buat_konteks_tls, pem_antara
from sibkd_mcp.sibkd_client import (
    KlienSibkd,
    SibkdError,
    adalah_halaman_login,
    baca_jawaban_json,
    baca_nama_pengguna,
    nama_berkas_aman,
)

BERANDA_LOGIN = f"""<html><body><a class="profile-pic"><span class="hidden-md-down">KING KONG &nbsp;</span></a>
<ul id="sidebarnav"><li><a href="{BASE}/usulan">Beranda</a></li></ul></body></html>"""


class SesiTiruan:
    """Pengganti requests.Session: tiap GET/POST dijawab dari antrean, permintaannya direkam."""

    def __init__(self, jawaban_get: list, jawaban_post: list):
        self.jawaban_get = list(jawaban_get)
        self.jawaban_post = list(jawaban_post)
        self.get_dikirim: list[tuple[str, dict]] = []
        self.post_dikirim: list[tuple[str, dict]] = []
        self.headers = {}

    def get(self, url, **kwargs):
        self.get_dikirim.append((url, kwargs))
        return self.jawaban_get.pop(0)

    def post(self, url, **kwargs):
        self.post_dikirim.append((url, kwargs))
        return self.jawaban_post.pop(0)


def klien_dengan(sesi: SesiTiruan) -> KlienSibkd:
    klien = KlienSibkd("0000000000", "sandi-karangan", base_url=BASE)
    klien.sesi_http = sesi
    return klien


def jawab_login_berhasil() -> list:
    return [JawabanTiruan(teks=BERANDA_LOGIN, url=f"{BASE}/usulan/usulan")]


# --- login -------------------------------------------------------------------


def test_login_mengirim_username_dan_password_dari_form():
    sesi = SesiTiruan([JawabanTiruan(teks=HALAMAN_LOGIN, url=f"{BASE}/login/login")], jawab_login_berhasil())
    klien = klien_dengan(sesi).login()

    url, kwargs = sesi.post_dikirim[0]
    assert url == f"{BASE}/login/login"
    assert kwargs["data"] == {"username": "0000000000", "password": "sandi-karangan"}
    assert klien.url_beranda == f"{BASE}/usulan/usulan"
    assert klien.nama == "KING KONG"


def test_login_ditolak_dikenali_dari_pengalihan_ke_form_login():
    """SIBKD tidak menulis pesan galat; tandanya hanya ?pesan=error di alamat."""
    sesi = SesiTiruan(
        [JawabanTiruan(teks=HALAMAN_LOGIN, url=f"{BASE}/login/login")],
        [JawabanTiruan(teks=HALAMAN_LOGIN, url=f"{BASE}/login/login?pesan=error")],
    )

    with pytest.raises(SibkdError, match="ditolak"):
        klien_dengan(sesi).login()


def test_kredensial_kosong_jatuh_ke_setelan():
    konfigurasi.atur_setelan(SIBKD_USERNAME="0000000000", SIBKD_PASSWORD="dari-setelan")
    klien = KlienSibkd()

    assert klien.username == "0000000000"
    assert klien.password == "dari-setelan"


def test_tanpa_kredensial_sama_sekali_ditolak_jelas():
    with pytest.raises(konfigurasi.KonfigurasiError, match="SIBKD_USERNAME"):
        KlienSibkd()


def test_halaman_login_dikenali():
    assert adalah_halaman_login(f"{BASE}/login/login?pesan=belumlogin")
    assert adalah_halaman_login(f"{BASE}/login/login")
    assert not adalah_halaman_login(f"{BASE}/dosen/bkdsister_v2")


def test_nama_pengguna_dari_kepala_halaman():
    assert baca_nama_pengguna(BERANDA_LOGIN) == "KING KONG"
    assert baca_nama_pengguna("<html></html>") == ""


# --- sesi habis --------------------------------------------------------------


def test_halaman_yang_dialihkan_ke_login_memicu_login_ulang():
    sesi = SesiTiruan(
        [
            JawabanTiruan(teks=HALAMAN_LOGIN, url=f"{BASE}/login/login?pesan=belumlogin"),
            JawabanTiruan(teks=HALAMAN_LOGIN, url=f"{BASE}/login/login"),
            JawabanTiruan(teks="<html>isi</html>", url=f"{BASE}/dosen/bkdsister_v2"),
        ],
        jawab_login_berhasil(),
    )
    jawaban = klien_dengan(sesi).ambil_halaman("/dosen/bkdsister_v2")

    assert jawaban.text == "<html>isi</html>"
    assert len(sesi.post_dikirim) == 1


def test_kirim_tidak_mengikuti_pengalihan_dan_mengulang_setelah_login():
    """Kalau 307 diikuti, requests mengirim ulang muatan (dan PDF) ke form login."""
    sesi = SesiTiruan(
        [JawabanTiruan(teks=HALAMAN_LOGIN, url=f"{BASE}/login/login")],
        [
            JawabanTiruan(status_code=307, headers={"Location": f"{BASE}/login/login?pesan=belumlogin"}),
            *jawab_login_berhasil(),
            JawabanTiruan(isi_json={"status": "success", "message": "Berhasil ditunda"}),
        ],
    )
    hasil = klien_dengan(sesi).kirim("/dosen/bkdsister_v2/tunda_proses/20/oktober")

    assert hasil == {"ok": True, "status": "success", "pesan": "Berhasil ditunda", "status_http": 200,
                     "mentah": {"status": "success", "message": "Berhasil ditunda"}}
    tujuan = [url for url, _ in sesi.post_dikirim]
    assert tujuan == [f"{BASE}/dosen/bkdsister_v2/tunda_proses/20/oktober", f"{BASE}/login/login",
                      f"{BASE}/dosen/bkdsister_v2/tunda_proses/20/oktober"]
    assert all(kwargs["allow_redirects"] is False for url, kwargs in sesi.post_dikirim if "tunda" in url)


# --- balasan JSON --------------------------------------------------------------


def test_balasan_json_sukses_dan_gagal():
    assert baca_jawaban_json(JawabanTiruan(isi_json={"status": "success", "message": "OK"}))["ok"] is True
    gagal = baca_jawaban_json(JawabanTiruan(isi_json={"status": "error", "message": "Periode ditutup"}))
    assert gagal["ok"] is False and gagal["pesan"] == "Periode ditutup"


def test_json_yang_dikirim_sebagai_teks_tetap_terbaca():
    """Endpoint api_jafung dan update_rwy_pend_sister diurai halaman dengan JSON.parse."""
    hasil = baca_jawaban_json(JawabanTiruan(teks='﻿{"status":"success","message":"Jafung tersinkron"}'))

    assert hasil["ok"] is True
    assert hasil["pesan"] == "Jafung tersinkron"


def test_balasan_bukan_json_dilaporkan_dengan_cuplikan():
    hasil = baca_jawaban_json(JawabanTiruan(teks="<html><h1>404 Page Not Found</h1></html>", status_code=404))

    assert hasil["ok"] is False
    assert "404 Page Not Found" in hasil["pesan"]


def test_status_success_dengan_http_galat_tidak_dianggap_berhasil():
    assert baca_jawaban_json(JawabanTiruan(isi_json={"status": "success"}, status_code=500))["ok"] is False


# --- unduhan -------------------------------------------------------------------


def test_unduh_menolak_host_lain(tmp_path):
    klien = klien_dengan(SesiTiruan([], []))

    with pytest.raises(SibkdError, match="luar SIBKD"):
        klien.unduh("https://contoh.com/x.pdf", tmp_path / "x.pdf")


def test_unduh_melewati_berkas_yang_sudah_ada(tmp_path):
    tujuan = tmp_path / "x.pdf"
    tujuan.write_bytes(b"lama")
    sesi = SesiTiruan([], [])

    assert klien_dengan(sesi).unduh(f"{BASE}/assets/x.pdf", tujuan) == (tujuan, False)
    assert sesi.get_dikirim == []


def test_unduh_menulis_berkas_dan_menolak_halaman_html(tmp_path):
    sesi = SesiTiruan(
        [
            JawabanTiruan(url=f"{BASE}/assets/x.pdf", isi=b"%PDF-1.4 isi", headers={"Content-Type": "application/pdf"}),
            JawabanTiruan(teks="<html></html>", url=f"{BASE}/assets/y.pdf", headers={"Content-Type": "text/html"}),
        ],
        [],
    )
    klien = klien_dengan(sesi)

    path, baru = klien.unduh(f"{BASE}/assets/x.pdf", tmp_path / "x.pdf")
    assert baru and path.read_bytes() == b"%PDF-1.4 isi"
    with pytest.raises(SibkdError, match="HTML"):
        klien.unduh(f"{BASE}/assets/y.pdf", tmp_path / "y.pdf")
    assert not (tmp_path / "y.pdf").exists()


def test_nama_berkas_tidak_bisa_keluar_folder():
    assert nama_berkas_aman("../../etc/passwd") == "passwd"
    assert nama_berkas_aman("File 2026:10.pdf") == "File 2026_10.pdf"
    assert nama_berkas_aman("") == "berkas.pdf"


# --- TLS -----------------------------------------------------------------------


def test_pem_antara_ikut_terpasang_bersama_paket():
    assert pem_antara().count("BEGIN CERTIFICATE") == 2


def test_konteks_tls_mengenal_sertifikat_antara_dan_tetap_memverifikasi():
    konteks = buat_konteks_tls()
    nama = {
        dict(bagian[0] for bagian in sertifikat["subject"]).get("commonName")
        for sertifikat in konteks.get_ca_certs()
    }

    assert "Sectigo Public Server Authentication CA DV R36" in nama
    assert konteks.verify_mode == ssl.CERT_REQUIRED
    assert konteks.check_hostname is True


def test_sesi_memakai_adaptor_tls_tanpa_mematikan_verifikasi():
    sesi = konfigurasi.buat_sesi_http()

    assert isinstance(sesi.get_adapter(f"{BASE}/"), AdaptorTls)
    assert sesi.verify is True


def test_ca_bundle_pengganti(tmp_path):
    bundel = tmp_path / "bundel.pem"
    bundel.write_text(pem_antara())
    konfigurasi.atur_setelan(ca_bundle=str(bundel))

    konteks = buat_konteks_tls()
    sesi = konfigurasi.buat_sesi_http()
    assert len(konteks.get_ca_certs()) == 2
    assert sesi.verify == str(bundel)


def test_ca_bundle_yang_salah_ditolak_jelas(tmp_path):
    konfigurasi.atur_setelan(SIBKD_CA_BUNDLE=str(tmp_path / "tidak-ada.pem"))

    with pytest.raises(konfigurasi.KonfigurasiError, match="tidak ada"):
        buat_konteks_tls()


def test_tidak_ada_jalan_mematikan_verifikasi():
    """Tidak ada setelan verify=False; sesi selalu memeriksa sertifikat."""
    sesi = konfigurasi.buat_sesi_http()
    adaptor = sesi.get_adapter(f"{BASE}/")

    assert adaptor.konteks.verify_mode == ssl.CERT_REQUIRED
    assert isinstance(sesi, requests.Session)

/**
 * Generate dokumen Nota Dinas (ND) sebagai PDF di sisi browser memakai
 * jsPDF + jsPDF-AutoTable, mengikuti tata letak template docx pada
 * static/templateND/ (lihat wiki/instructions/GENERATE_ND.MD).
 *
 * Dipakai oleh templates/pakln/preview_nd.html. Diekspos sebagai
 * `window.NotaDinasPDF.generate(data)` -> instance jsPDF (belum disimpan).
 *
 * `data` (semua string, employees adalah array):
 *   nama_display, negara_display, keperluan, nama_unor, sumber_biaya_display,
 *   jabatan_dari, nama_pejabat, paraf_ketua_tim_aki, nama_karo_pakln,
 *   paraf_katim_aki_nd2, paraf_plt_kabag_kln_nd2,
 *   employees: [{ no, nama, nip, jabatan, periode, h_kerja, h_kalender }, ...]
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.NotaDinasPDF = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var PAGE_W = 148;
  var PAGE_H = 210;
  var MARGIN_L = 16;
  var MARGIN_R = 16;
  var CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R;
  var LABEL_W = 24;

  function drawKop(doc, y) {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(11);
    doc.text("KEMENTERIAN PEKERJAAN UMUM", PAGE_W / 2, y, { align: "center" });
    y += 4.5;
    doc.text("SEKRETARIAT JENDERAL", PAGE_W / 2, y, { align: "center" });
    y += 4.5;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(7.5);
    doc.text(
      "Jalan Pattimura Nomor 20, Kebayoran Baru, Jakarta Selatan 12110, Telepon (021)7392681, Surel:bpakln@pu.go.id",
      PAGE_W / 2, y, { align: "center" }
    );
    y += 2.5;
    doc.setLineWidth(0.6);
    doc.line(MARGIN_L, y, PAGE_W - MARGIN_R, y);
    y += 1.2;
    doc.setLineWidth(0.2);
    doc.line(MARGIN_L, y, PAGE_W - MARGIN_R, y);
    y += 6;
    return y;
  }

  function drawJudul(doc, y, withNomor) {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(12);
    doc.text("NOTA DINAS", PAGE_W / 2, y, { align: "center" });
    y += 5;
    if (withNomor) {
      doc.setFont("helvetica", "normal");
      doc.setFontSize(9);
      doc.text("NOMOR:", PAGE_W / 2, y, { align: "center" });
      y += 5;
    }
    return y;
  }

  function drawField(doc, y, label, value) {
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9.5);
    doc.text(label, MARGIN_L, y);
    doc.text(":", MARGIN_L + LABEL_W, y);
    var lines = doc.splitTextToSize(value || "-", CONTENT_W - LABEL_W - 3);
    doc.text(lines, MARGIN_L + LABEL_W + 3, y);
    return y + lines.length * 4.2;
  }

  function drawParagraph(doc, y, text, indent) {
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9.5);
    var x = MARGIN_L + (indent || 0);
    var lines = doc.splitTextToSize(text, CONTENT_W - (indent || 0));
    doc.text(lines, x, y, { align: "justify", maxWidth: CONTENT_W - (indent || 0) });
    return y + lines.length * 4.4 + 2.5;
  }

  function drawParafBoxes(doc, y, boxes) {
    // `boxes`: array label -> menggambar kotak paraf berdampingan.
    var boxW = 30;
    var boxH = 16;
    var gap = 4;
    var totalW = boxes.length * boxW + (boxes.length - 1) * gap;
    var x = PAGE_W - MARGIN_R - totalW;
    doc.setDrawColor(0);
    doc.setLineWidth(0.3);
    doc.setFontSize(7.5);
    doc.setFont("helvetica", "normal");
    boxes.forEach(function (label) {
      doc.rect(x, y, boxW, boxH);
      doc.text(label || "-", x + boxW / 2, y + 5, { align: "center", maxWidth: boxW - 2 });
      x += boxW + gap;
    });
    return y + boxH;
  }

  function drawTandaTangan(doc, y, jabatanLines, nama) {
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9.5);
    jabatanLines.forEach(function (line, i) {
      doc.text(line, MARGIN_L, y + i * 4.2);
    });
    y += jabatanLines.length * 4.2 + 16;
    doc.setFont("helvetica", "bold");
    doc.text(nama || "-", MARGIN_L, y);
    return y + 6;
  }

  function buildNd1(doc, data, withParaf) {
    var y = drawKop(doc, 14);
    y = drawJudul(doc, y, false);
    y = drawField(doc, y, "Yth.", "Kepala Biro Perencanaan Anggaran dan Kerja Sama Luar Negeri");
    y = drawField(doc, y, "Dari", data.jabatan_dari);
    y = drawField(
      doc, y, "Hal",
      "Penyampaian Konsep Permohonan Izin Melakukan Perjalanan Luar Negeri a.n. " +
      data.nama_display + " ke " + data.negara_display
    );
    y = drawField(doc, y, "Tanggal", " ");
    y += 3;
    y = drawParagraph(
      doc, y,
      "Sehubungan dengan keperluan administrasi pegawai dalam melakukan perjalanan ke luar negeri " +
      "non-dinas, bersama ini kami sampaikan dengan hormat konsep Nota Dinas Permohonan Izin " +
      "Melakukan Perjalanan Luar Negeri a.n. " + data.nama_display + " ke " + data.negara_display +
      ", dari Kepala Biro Perencanaan Anggaran dan Kerja Sama Luar Negeri kepada Sekretaris " +
      "Jenderal, untuk kami mohonkan perkenan arahan dan petunjuk lebih lanjut."
    );
    y = drawParagraph(
      doc, y,
      "Demikian kami sampaikan, atas perhatian dan perkenan arahan lebih lanjut, kami ucapkan " +
      "terima kasih."
    );
    y += 10;
    y = drawTandaTangan(doc, y, ["Plt. Kepala Bagian", "Kerja Sama Luar Negeri,"], data.nama_pejabat);
    if (withParaf) {
      drawParafBoxes(doc, y + 6, [data.paraf_ketua_tim_aki]);
    }
  }

  function buildNd2(doc, data, withParaf) {
    var y = drawKop(doc, 14);
    y = drawJudul(doc, y, true);
    y = drawField(doc, y, "Yth.", "Sekretaris Jenderal Kementerian Pekerjaan Umum");
    y = drawField(doc, y, "Dari", "Kepala Biro Perencanaan Anggaran dan Kerja Sama Luar Negeri");
    y = drawField(
      doc, y, "Hal",
      "Permohonan Izin Melakukan Perjalanan Luar Negeri a.n. " + data.nama_display +
      " ke " + data.negara_display + " dalam rangka " + data.keperluan
    );
    y = drawField(doc, y, "Tanggal", " ");
    y += 3;
    y = drawParagraph(
      doc, y,
      "Sehubungan dengan keperluan administrasi pegawai dalam melakukan perjalanan ke luar negeri " +
      "non-kedinasan, bersama ini kami sampaikan dengan hormat permohonan Persetujuan Izin " +
      "Perjalanan ke Luar Negeri sebagai berikut:"
    );
    y = drawField(doc, y, "1. Tujuan Negara", data.negara_display);
    y = drawField(doc, y, "2. Maksud/Tujuan", data.keperluan);
    y = drawField(doc, y, "3. Unit Organisasi", data.nama_unor);
    y = drawField(doc, y, "4. Sumber Pembiayaan", data.sumber_biaya_display);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9.5);
    doc.text("5. Data Pegawai:", MARGIN_L, y);
    y += 3;

    doc.autoTable({
      startY: y,
      margin: { left: MARGIN_L, right: MARGIN_R },
      styles: { fontSize: 8, cellPadding: 1.5, halign: "center", valign: "middle" },
      headStyles: { fillColor: [235, 235, 235], textColor: 0, fontStyle: "bold" },
      columnStyles: { 0: { cellWidth: 10 }, 3: { cellWidth: 34 } },
      head: [["No.", "Nama/NIP", "Jabatan", "Periode Perjalanan"]],
      body: (data.employees || []).map(function (e) {
        return [
          e.no,
          e.nama + "\n" + e.nip,
          e.jabatan,
          e.periode + "\n" + e.h_kerja + " hari kerja/\n" + e.h_kalender + " hari kalender",
        ];
      }),
    });
    y = doc.lastAutoTable.finalY + 5;

    y = drawParagraph(
      doc, y,
      "Dapat kami sampaikan bahwa permohonan Persetujuan Izin Perjalanan ke Luar Negeri dimaksud, " +
      "telah mendapat persetujuan Menteri Pekerjaan Umum sebagaimana terlampir."
    );
    y = drawParagraph(
      doc, y,
      "Demikian kami sampaikan, atas perhatian dan perkenan arahan lebih lanjut, kami ucapkan " +
      "terima kasih."
    );
    y += 10;
    y = drawTandaTangan(
      doc, y,
      ["Kepala Biro Perencanaan Anggaran dan", "Kerja Sama Luar Negeri"],
      data.nama_karo_pakln
    );
    if (withParaf) {
      drawParafBoxes(doc, y + 6, [data.paraf_katim_aki_nd2, data.paraf_plt_kabag_kln_nd2]);
    }
  }

  function generate(data, jsPDFCtor) {
    var JsPdf = jsPDFCtor || (typeof window !== "undefined" && window.jspdf && window.jspdf.jsPDF);
    if (!JsPdf) {
      throw new Error("jsPDF tidak ditemukan — pastikan library sudah dimuat.");
    }
    var doc = new JsPdf({ unit: "mm", format: "a5", orientation: "portrait" });

    buildNd1(doc, data, true);
    doc.addPage("a5", "portrait");
    buildNd1(doc, data, false);
    doc.addPage("a5", "portrait");
    buildNd2(doc, data, true);
    doc.addPage("a5", "portrait");
    buildNd2(doc, data, false);

    return doc;
  }

  return { generate: generate };
});

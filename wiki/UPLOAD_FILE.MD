# Mekanisme Upload File (MinIO-based) — Panduan Implementasi

Dokumen ini menjabarkan mekanisme upload, akses, dan hapus file yang dipakai di project EILN, agar bisa direplikasi di project Next.js lain. Backend penyimpanan menggunakan **MinIO** (S3-compatible object storage), diakses lewat API route Next.js yang di-proxy (bukan diakses langsung dari browser), dengan proteksi autentikasi sesi (NextAuth) dan token JWT sementara untuk viewing.

## 1. Arsitektur Singkat

```
Browser (multipart/form-data)
   │
   ▼
POST /api/files/upload  ──▶  authMiddleware (session check)
   │                              │
   │                              ▼
   │                         formidable (parse + validasi tipe/ukuran)
   │                              │
   │                              ▼
   │                         minioClient.uploadFile()
   │                              │
   │                              ▼
   │                         MinIO Bucket (object storage)
   ▼
Response { filePath, url, ... }

GET  /api/files/[...path]?token=...   →  verifikasi JWT / session  →  stream file dari MinIO
POST /api/files/token                 →  generate JWT sementara untuk 1 file (exp 1 jam)
DELETE /api/files/delete              →  hapus object dari MinIO
```

Prinsip penting:
- File **tidak pernah diakses langsung** via URL publik MinIO — semua lewat proxy API Next.js supaya bisa dikontrol autentikasi & autorisasinya.
- Nama file asli tidak dipakai sebagai object key — diganti UUID untuk mencegah collision & directory traversal.
- Endpoint viewer mendukung dua mode auth: session (cookie NextAuth) atau token JWT short-lived (untuk dipakai di `<iframe>`/`<img>` tanpa cookie).

## 2. Dependencies

```json
{
  "minio": "^8.0.2",
  "formidable": "^3.5.2",
  "uuid": "^10.0.0",
  "jose": "^5.9.4",
  "next-auth": "^4.24.11"
}
```

Install:
```bash
npm install minio formidable uuid jose next-auth
```

## 3. Variabel Konfigurasi (Environment Variables)

Salin ke `.env` project tujuan, sesuaikan nilainya:

```env
# --- MinIO server-side (dipakai oleh backend Next.js API routes) ---
MINIO_ENDPOINT=10.130.10.102          # host MinIO (nama service docker, IP, atau domain)
MINIO_PORT=9000
MINIO_USE_SSL=false                   # true jika MinIO di belakang HTTPS
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=nama-bucket-anda

# --- Endpoint alternatif untuk resolusi backend di dalam Docker ---
# Dipakai oleh minioClient sebagai override endpoint (mis. nama service compose)
NEXT_PUBLIC_MINIO_ENDPOINT_BACKEND=minio

# --- Variabel NEXT_PUBLIC_* (fallback / dipakai jika ada kebutuhan client-side) ---
NEXT_PUBLIC_MINIO_ENDPOINT=10.130.10.102
NEXT_PUBLIC_MINIO_PORT=9000
NEXT_PUBLIC_MINIO_ACCESS_KEY=minioadmin
NEXT_PUBLIC_MINIO_SECRET_KEY=minioadmin
NEXT_PUBLIC_MINIO_BUCKET_NAME=nama-bucket-anda
NEXT_PUBLIC_MINIO_USE_SSL=false

# --- Presigned URL (opsional, jika dipakai) ---
MINIO_PRESIGNED_URL_EXPIRY=604800             # detik, maksimal 7 hari (batas MinIO)
NEXT_PUBLIC_MINIO_PRESIGNED_URL_EXPIRY=604800

# --- MinIO root credential (untuk container MinIO itu sendiri, docker-compose) ---
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# --- Untuk MinIO Client CLI (mc), opsional ---
MC_HOST_myminio=http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@minio:9000

# --- Secret untuk signing token akses file sementara ---
ACCESS_TOKEN_SECRET=ganti_dengan_secret_acak_minimal_32_karakter

# --- NextAuth (dibutuhkan authMiddleware untuk session check) ---
NEXTAUTH_SECRET=ganti_dengan_secret_acak
NEXTAUTH_URL=http://localhost:3000
```

Catatan resolusi endpoint (lihat `minioClient.js`):
- Endpoint yang benar-benar dipakai server: `NEXT_PUBLIC_MINIO_ENDPOINT_BACKEND` → fallback `MINIO_ENDPOINT` → fallback default `"minio"`.
- Port: `MINIO_PORT` → fallback `NEXT_PUBLIC_MINIO_PORT` → default `9000`.
- Access/secret key & SSL flag punya pola fallback yang sama (server var lalu `NEXT_PUBLIC_*`).
- Bucket name: `MINIO_BUCKET_NAME` → fallback `NEXT_PUBLIC_MINIO_BUCKET_NAME`. **Wajib diisi**, kalau kosong upload akan gagal dengan error eksplisit.

## 4. Infrastruktur (Docker Compose)

```yaml
minio:
  container_name: app-minio
  image: minio/minio:RELEASE.2025-02-28T09-55-16Z
  ports:
    - "9000:9000"   # API
    - "9001:9001"   # Console web
  volumes:
    - minio_data:/data
  environment:
    - MINIO_ROOT_USER=${MINIO_ROOT_USER}
    - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}
  command: server /data --console-address ":9001"
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
    interval: 30s
    timeout: 20s
    retries: 3
  restart: unless-stopped
  networks:
    - app-network

# Opsional: auto-create bucket saat startup
minio-init:
  image: minio/mc:latest
  depends_on:
    minio:
      condition: service_healthy
  entrypoint: >
    /bin/sh -c "
    mc alias set myminio http://minio:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD;
    mc mb myminio/nama-bucket-anda --ignore-existing;
    "
  networks:
    - app-network

volumes:
  minio_data:
```

Alternatif: bucket juga bisa dibuat lewat pemanggilan `POST /api/files/init-minio` sekali setelah deploy (lihat §6.5) — otomatis membuat bucket jika belum ada.

## 5. Struktur File yang Perlu Dibuat

```
src/
├── utils/
│   └── minioClient.js          # koneksi MinIO + fungsi upload/delete/presign
├── middleware/
│   └── authMiddleware.js       # wrapper auth (session-based) untuk API routes
└── pages/api/files/
    ├── upload.js                # POST — upload file
    ├── delete.js                # DELETE — hapus file
    ├── token.js                 # POST — generate token akses sementara
    ├── [...path].js             # GET/HEAD — proxy stream file (viewer)
    └── init-minio.js            # POST — bootstrap bucket (opsional)
```

## 6. Implementasi

### 6.1 `src/utils/minioClient.js` — Client & fungsi inti

```javascript
import { Client } from "minio";
import path from "path";

const getMinioEndpoint = () => {
  return process.env.NEXT_PUBLIC_MINIO_ENDPOINT_BACKEND || process.env.MINIO_ENDPOINT || "minio";
};

const minioEndpoint = getMinioEndpoint();
const minioPort = parseInt(process.env.MINIO_PORT || process.env.NEXT_PUBLIC_MINIO_PORT || "9000");
const minioUseSSL = process.env.MINIO_USE_SSL === "true" || process.env.NEXT_PUBLIC_MINIO_USE_SSL === "true";
const minioAccessKey = process.env.MINIO_ACCESS_KEY || process.env.NEXT_PUBLIC_MINIO_ACCESS_KEY || "minioadmin";
const minioSecretKey = process.env.MINIO_SECRET_KEY || process.env.NEXT_PUBLIC_MINIO_SECRET_KEY || "minioadmin";

const minioClient = new Client({
  endPoint: minioEndpoint,
  port: minioPort,
  useSSL: minioUseSSL,
  accessKey: minioAccessKey,
  secretKey: minioSecretKey,
});

export const uploadFile = async (file, uploadPath, uniqueFilename) => {
  try {
    const bucketName = process.env.MINIO_BUCKET_NAME || process.env.NEXT_PUBLIC_MINIO_BUCKET_NAME;
    if (!bucketName) {
      throw new Error("MinIO bucket name is not configured. Please set MINIO_BUCKET_NAME");
    }

    const bucketExists = await minioClient.bucketExists(bucketName);
    if (!bucketExists) {
      await minioClient.makeBucket(bucketName, "us-east-1");
    }

    const metaData = { "Content-Type": file.mimetype || "application/octet-stream" };
    const objectName = uniqueFilename ? path.join(uploadPath, uniqueFilename) : uploadPath;
    const buffer = await require("fs").promises.readFile(file.filepath);

    await minioClient.putObject(bucketName, objectName, buffer, metaData);

    return { success: true, objectName, url: objectName, Location: objectName };
  } catch (error) {
    return { success: false, error: error.message };
  }
};

export const deleteFile = async (fileUrl) => {
  try {
    if (!fileUrl) return { success: true };
    const bucketName = process.env.MINIO_BUCKET_NAME || process.env.NEXT_PUBLIC_MINIO_BUCKET_NAME;

    let objectName = fileUrl.split("?")[0];
    const relativePrefix = `/${bucketName}/`;
    if (objectName.startsWith(relativePrefix)) objectName = objectName.substring(relativePrefix.length);
    if (objectName.startsWith(bucketName + "/")) objectName = objectName.substring(bucketName.length + 1);

    await minioClient.removeObject(bucketName, objectName);
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
};

export const getPresignedUrl = async (objectName, expiry = 7 * 24 * 60 * 60) => {
  try {
    const bucketName = process.env.MINIO_BUCKET_NAME || process.env.NEXT_PUBLIC_MINIO_BUCKET_NAME;
    const maxExpiry = 7 * 24 * 60 * 60;
    const validExpiry = Math.min(Math.max(expiry, 60), maxExpiry);
    const presignedUrl = await minioClient.presignedGetObject(bucketName, objectName, validExpiry);
    return { success: true, url: presignedUrl, objectName, expiresIn: validExpiry };
  } catch (error) {
    return { success: false, error: error.message };
  }
};

export default minioClient;
```

> Catatan: fungsi `deleteFile` di atas disederhanakan (versi asli EILN juga menstrip prefix URL `http://host:port/bucket/`, sesuaikan bila Anda menyimpan `filePath` sebagai full URL, bukan object key relatif).

### 6.2 `src/middleware/authMiddleware.js` — Proteksi sesi

```javascript
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config"; // sesuaikan path config NextAuth Anda

export function authMiddleware(handler) {
  return async (req, res) => {
    try {
      const session = await getServerSession(req, res, authOptions);
      if (!session?.user) {
        return res.status(401).json({ message: "Authentication required" });
      }
      req.user = { id: session.user.id, ...session.user };
      return handler(req, res);
    } catch (error) {
      return res.status(401).json({ message: "Authentication failed", error: error.message });
    }
  };
}
```

### 6.3 `src/pages/api/files/upload.js` — Endpoint upload

```javascript
import { authMiddleware } from "../../../middleware/authMiddleware";
import { uploadFile } from "../../../utils/minioClient";
import formidable from "formidable";
import { v4 as uuidv4 } from "uuid";
import path from "path";

// WAJIB: matikan bodyParser bawaan Next.js agar formidable bisa parse multipart
export const config = {
  api: { bodyParser: false },
};

const ALLOWED_TYPES = [
  "application/pdf",
  "image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
];

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB — sesuaikan kebutuhan

async function handleFileUpload(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ message: "Method not allowed" });
  }

  try {
    const form = formidable({
      multiples: false,
      maxFileSize: MAX_FILE_SIZE,
      allowEmptyFiles: false,
      filter: ({ mimetype }) => ALLOWED_TYPES.includes(mimetype),
    });

    const [fields, files] = await form.parse(req);

    const uploadPath = fields.uploadPath?.[0];
    const category = fields.category?.[0] || "general";

    if (!uploadPath) {
      return res.status(400).json({ message: "Upload path is required" });
    }

    const fileKey = Object.keys(files)[0];
    const uploadedFile = files[fileKey]?.[0];
    if (!uploadedFile) {
      return res.status(400).json({ message: "No file uploaded" });
    }

    const fileExtension = path.extname(uploadedFile.originalFilename || "");
    const uniqueFilename = `${uuidv4()}${fileExtension}`;
    const fullUploadPath = `${category}/${uploadPath}`;

    const uploadResult = await uploadFile(uploadedFile, fullUploadPath, uniqueFilename);
    if (!uploadResult.success) {
      return res.status(500).json({ message: "Failed to upload file", error: uploadResult.error });
    }

    return res.status(200).json({
      message: "File uploaded successfully",
      data: {
        filePath: uploadResult.objectName,
        originalFilename: uploadedFile.originalFilename,
        size: uploadedFile.size,
        mimetype: uploadedFile.mimetype,
        url: uploadResult.url,
      },
    });
  } catch (error) {
    if (error.code === "LIMIT_FILE_SIZE") {
      return res.status(413).json({ message: "File too large" });
    }
    return res.status(500).json({ message: "Internal server error", error: error.message });
  }
}

export default authMiddleware(handleFileUpload);
```

### 6.4 `src/pages/api/files/[...path].js` — Proxy viewer (stream file)

```javascript
import { authMiddleware } from "../../../middleware/authMiddleware";
import minioClient from "../../../utils/minioClient";
import { jwtVerify } from "jose";

async function handleFileProxy(req, res) {
  if (req.method !== "GET" && req.method !== "HEAD") {
    return res.status(405).json({ message: "Method not allowed" });
  }

  const { path, token } = req.query;
  if (!path || !Array.isArray(path)) {
    return res.status(400).json({ message: "Invalid file path" });
  }

  const objectName = path.join("/");
  const bucketName = process.env.MINIO_BUCKET_NAME || process.env.NEXT_PUBLIC_MINIO_BUCKET_NAME;

  // Mode token: untuk dipakai di <img>/<iframe> tanpa cookie session
  if (token) {
    try {
      const secretKey = new TextEncoder().encode(
        (process.env.ACCESS_TOKEN_SECRET || "fallback-secret").slice(0, 32)
      );
      const { payload } = await jwtVerify(token, secretKey);
      if (payload.filePath !== objectName) {
        return res.status(403).json({ message: "Token is not valid for this file" });
      }
    } catch (error) {
      return res.status(401).json({ message: "Invalid or expired token" });
    }
  }

  try {
    const objectStat = await minioClient.statObject(bucketName, objectName);
    const contentType = objectStat?.metaData?.["content-type"] || "application/octet-stream";
    const filename = objectName.split("/").pop();

    res.setHeader("Content-Type", contentType);
    res.setHeader("Content-Disposition", `inline; filename="${filename}"`);
    res.setHeader("Cache-Control", "public, max-age=3600");
    res.setHeader("X-Frame-Options", "SAMEORIGIN");

    if (req.method === "HEAD") return res.status(200).end();

    const stream = await minioClient.getObject(bucketName, objectName);
    stream.pipe(res);
    stream.on("error", () => {
      if (!res.headersSent) res.status(500).json({ message: "Error streaming file" });
    });
  } catch (error) {
    return res.status(404).json({ message: "File not found" });
  }
}

// Bypass session auth kalau ada token valid; selain itu wajib session
async function authWrapper(req, res) {
  if (req.query.token) return handleFileProxy(req, res);
  return authMiddleware(handleFileProxy)(req, res);
}

export default authWrapper;
```

### 6.5 `src/pages/api/files/token.js` — Token akses sementara

```javascript
import { authMiddleware } from "../../../middleware/authMiddleware";
import { SignJWT } from "jose";

async function generateFileToken(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ message: "Method not allowed" });
  }

  const { filePath } = req.body;
  if (!filePath) {
    return res.status(400).json({ message: "File path is required" });
  }

  const secretKey = new TextEncoder().encode(
    (process.env.ACCESS_TOKEN_SECRET || "fallback-secret").slice(0, 32)
  );

  const fileToken = await new SignJWT({ filePath, userId: req.user.id })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("1h")
    .sign(secretKey);

  return res.status(200).json({
    message: "File token generated successfully",
    data: { token: fileToken, filePath, expiresIn: 3600 },
  });
}

export default authMiddleware(generateFileToken);
```

### 6.6 `src/pages/api/files/delete.js` — Hapus file

```javascript
import { authMiddleware } from "../../../middleware/authMiddleware";
import { deleteFile } from "../../../utils/minioClient";

async function handleFileDelete(req, res) {
  if (req.method !== "DELETE") {
    return res.status(405).json({ message: "Method not allowed" });
  }

  const { filePath } = req.body;
  if (!filePath) {
    return res.status(400).json({ message: "File path is required" });
  }

  const result = await deleteFile(filePath);
  if (!result.success) {
    return res.status(500).json({ message: "Failed to delete file", error: result.error });
  }

  return res.status(200).json({ message: "File deleted successfully", data: { filePath, deleted: true } });
}

export default authMiddleware(handleFileDelete);
```

### 6.7 `src/pages/api/files/init-minio.js` — Bootstrap bucket (opsional, jalankan sekali)

```javascript
import minioClient from "../../../utils/minioClient";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ message: "Method not allowed" });
  }

  const bucketName = process.env.MINIO_BUCKET_NAME || process.env.NEXT_PUBLIC_MINIO_BUCKET_NAME;
  if (!bucketName) {
    return res.status(500).json({ message: "MINIO_BUCKET_NAME is missing" });
  }

  const exists = await minioClient.bucketExists(bucketName);
  if (!exists) {
    await minioClient.makeBucket(bucketName, "us-east-1");
    return res.status(200).json({ message: "Bucket created", data: { bucketName, created: true } });
  }
  return res.status(200).json({ message: "Bucket already exists", data: { bucketName, created: false } });
}
```

## 7. Pemakaian di Frontend

```javascript
// Upload
async function uploadFile(file, uploadPath, category = "documents") {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("uploadPath", uploadPath);   // mis. "pegawai/<uuid>"
  formData.append("category", category);

  const res = await fetch("/api/files/upload", { method: "POST", body: formData });
  return res.json(); // { data: { filePath, url, ... } }
}

// Lihat file (session-based, contoh langsung di <a>/<iframe> yang bisa bawa cookie)
const viewUrl = `/api/files/${filePath}`;

// Lihat file tanpa cookie (mis. dibuka di tab/aplikasi lain) — generate token dulu
async function getFileViewUrl(filePath) {
  const res = await fetch("/api/files/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filePath }),
  });
  const { data } = await res.json();
  return `/api/files/${filePath}?token=${data.token}`;
}

// Hapus file
async function removeFile(filePath) {
  const res = await fetch("/api/files/delete", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filePath }),
  });
  return res.json();
}
```

## 8. Checklist Implementasi di Project Baru

1. Jalankan MinIO (docker-compose atau layanan terkelola) dan siapkan bucket.
2. Install dependencies: `minio`, `formidable`, `uuid`, `jose`, `next-auth`.
3. Salin variabel environment di §3, sesuaikan credential & nama bucket.
4. Buat `minioClient.js`, `authMiddleware.js`, dan 5 API route di §6.
5. Pastikan `authOptions` NextAuth sudah terkonfigurasi (dipakai `authMiddleware`) — jika project tidak pakai NextAuth, ganti pengecekan session dengan mekanisme auth yang dipakai project tersebut.
6. Panggil `POST /api/files/init-minio` sekali setelah deploy untuk memastikan bucket tersedia (atau buat lewat `mc mb` / compose init service).
7. Sesuaikan `ALLOWED_TYPES` dan `MAX_FILE_SIZE` di `upload.js` sesuai kebutuhan domain aplikasi.
8. Simpan `filePath`/`objectName` hasil upload (bukan full URL MinIO) ke database, supaya proxy viewer & delete tetap bekerja walau endpoint MinIO berubah.

## 9. Catatan Keamanan

- Jangan pernah expose endpoint MinIO langsung ke publik / bucket policy public-read — semua akses harus lewat proxy `[...path].js` supaya autentikasi & otorisasi tetap berlaku.
- `ACCESS_TOKEN_SECRET` harus acak, minimal 32 karakter, dan berbeda dari secret NextAuth.
- Validasi `mimetype` di `formidable filter` mencegah upload tipe file berbahaya (mis. `.exe`, `.sh`), tapi tetap pertimbangkan validasi tambahan (mis. cek magic bytes) untuk kasus sensitif.
- Nama file diganti UUID untuk mencegah overwrite dan path traversal — jangan gunakan `originalFilename` langsung sebagai object key.
- Expiry token viewer default 1 jam; presigned URL maksimal 7 hari (batasan MinIO/S3 signature v4).

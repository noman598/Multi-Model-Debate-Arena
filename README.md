# FastAPI PicShare & Authentication System

A unified, integrated application combining **JWT Authentication with Redis Refresh Tokens** and the **PicShare Photo Gallery** with 200x200 thumbnails.

Designed with clean boundaries for direct migration to **AWS (S3, Lambda, SNS, RDS)**.

---

## 1. Quick Start

### Step 1: (Optional) Start PostgreSQL
If using PostgreSQL instead of SQLite:
```bash
docker compose up -d
```
*(Or keep `DATABASE_URL="sqlite:///./auth_database.db"` in `.env` to run on SQLite with zero setup!)*

### Step 2: Start the FastAPI Server
```powershell
.venv\Scripts\activate
python main.py
```
*(Or use `uvicorn main:app --reload --host 127.0.0.1 --port 8000`)*

### Step 3: Open in Browser
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)**:
1. **Sign Up / Log In**: Authenticate via the existing JWT HttpOnly cookie flow.
2. **PicShare Gallery**:
   - Upload any JPG or PNG image (max 5 MB).
   - An automatic 200x200 thumbnail is generated using Pillow.
   - A notification message prints to your terminal console.
   - Click any thumbnail to view the full-size original image.
   - Click **Delete** to delete both the original, thumbnail, and database record.
3. **Session Actions**: Test `/api/auth/me`, `/api/auth/refresh`, and `/api/auth/logout`.

---

## 2. Integrated Architecture

| File | Purpose | AWS Readiness |
| :--- | :--- | :--- |
| [app/storage.py](file:///d:/dev/dwing/app/storage.py) | `save_file` & `delete_file` | Ready to swap inner calls with **AWS S3** (`boto3.client('s3')`) |
| [app/thumbnails.py](file:///d:/dev/dwing/app/thumbnails.py) | Standalone `generate_thumbnail` (200x200) | Pure function (`bytes -> bytes`), ready for **AWS Lambda** |
| [app/notifications.py](file:///d:/dev/dwing/app/notifications.py) | `send_photo_notification` | Prints to console, ready to swap with **AWS SNS** |
| [app/database.py](file:///d:/dev/dwing/app/database.py) | SQLAlchemy engine & session | Reads `DATABASE_URL` from `.env`, ready for **AWS RDS** |
| [app/models.py](file:///d:/dev/dwing/app/models.py) | `User` and `Photo` database models | Relates users to their uploaded photos |
| [app/dependencies.py](file:///d:/dev/dwing/app/dependencies.py) | `get_current_user` auth dependency | Validates incoming JWT cookies |
| [app/routers/photos.py](file:///d:/dev/dwing/app/routers/photos.py) | `/api/photos` upload, list, delete | Protected by the existing auth dependency |
| [app/routers/auth.py](file:///d:/dev/dwing/app/routers/auth.py) | `/signup`, `/login`, `/refresh`, `/logout` | Core authentication endpoints |
| [app/static/](file:///d:/dev/dwing/app/static) | Minimal beige prototype UI | Form controls, live photo grid, response inspector |
| [docker-compose.yml](file:///d:/dev/dwing/docker-compose.yml) | Postgres container on port 5432 | Optional local PostgreSQL |

# 🌐 Hostinger Deployment Guide for AgriDSS & PMFBY Pricing

This guide provides step-by-step instructions for deploying **AgriDSS** (including the integrated **PMFBY Actuarial Pricing** module) to Hostinger.

---

## 📌 Choose Your Hostinger Hosting Plan

| Hosting Type | Supported? | Recommended? | Key Advantage |
| :--- | :---: | :---: | :--- |
| **Hostinger VPS (KVM 1 / KVM 2 / KVM 4)** | ✅ Yes | ⭐⭐⭐ **Strongly Recommended** | Dedicated RAM/CPU, full root SSH access, handles heavy scientific libraries (`numpy`, `scipy`, `pandas`), zero timeout limits, free SSL. |
| **Hostinger Cloud / Business Web Hosting** | ✅ Yes | ⭐⭐ **Supported** | Uses hPanel "Setup Python App" with CloudLinux Passenger WSGI. No server administration needed. |

---

## 🚀 Method 1: Hostinger VPS (Recommended — 5 Minutes)

### Step 1: Connect to your Hostinger VPS via SSH
From your computer terminal or PowerShell:
```bash
ssh root@YOUR_SERVER_IP
```

### Step 2: Upload or Clone the Code
```bash
# Option A: Clone from Git
git clone <your-repo-url> /var/www/agridss
cd /var/www/agridss

# Option B: Or upload your project zip via SCP/SFTP from your PC:
# scp -r D:\AGRIDSS\* root@YOUR_SERVER_IP:/var/www/agridss/
```

### Step 3: Run the Automated Setup Script
```bash
cd /var/www/agridss
chmod +x deploy_hostinger_vps.sh
./deploy_hostinger_vps.sh
```

The script will automatically:
- Install Python 3.11, Nginx, pip, and compilation headers.
- Create a Python virtual environment and install all packages from `requirements.txt`.
- Set up a systemd background service (`agridss.service`) running Gunicorn with 4 workers.
- Configure Nginx reverse proxy on port 80.

### Step 4: Configure Free SSL (HTTPS)
Run Certbot to secure your domain with free Let's Encrypt SSL:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### Step 5: Verify Service
```bash
sudo systemctl status agridss
```
Your application will be live at `https://yourdomain.com`!

---

## 🐳 Method 1B: Hostinger VPS with Docker (Alternative)

If your Hostinger VPS has Docker installed (or using Hostinger's "Docker on Ubuntu" template):

```bash
cd /var/www/agridss
docker compose up -d --build
```
The app will build and run in an isolated production container on port 5000.

---

## ☁️ Method 2: Hostinger Shared / Cloud Hosting (hPanel)

If you are using Hostinger Web or Cloud Hosting with **hPanel**:

### Step 1: Upload Files
1. Open **Hostinger hPanel** $\to$ **File Manager**.
2. Navigate to your domain directory (e.g. `public_html` or create a subfolder `/agridss`).
3. Upload all files from `D:\AGRIDSS` (you can zip them locally, upload the zip, and click **Extract**).

### Step 2: Set Up Python Application in hPanel
1. In hPanel, search for **Python** or go to **Advanced $\to$ Setup Python App**.
2. Click **Create Application**:
   - **Python Version**: Select **3.10** or **3.11**.
   - **Application Root**: `agridss` (the directory where files are placed).
   - **Application URL**: `yourdomain.com` (or subdomain `pricing.yourdomain.com`).
   - **Application Startup File**: `passenger_wsgi.py` *(already created for you)*.
   - **Application Entry Point**: `application`.
3. Click **Create**.

### Step 3: Install Python Dependencies
1. After creating, hPanel will display a command to activate the virtual environment:
   ```bash
   source /home/u123456789/virtualenv/agridss/3.11/bin/activate
   ```
2. Open the **Terminal** in hPanel (or SSH into your shared hosting account).
3. Paste and run the activation command.
4. Run:
   ```bash
   cd ~/agridss
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

### Step 4: Add Environment Variables
1. Ensure the `.env` file exists in your app root (`~/agridss/.env`).
2. Set your production `SECRET_KEY` and credentials.

### Step 5: Restart the Application
In hPanel $\to$ **Python App**, click **Restart Application**.

Open your domain in the browser to access the dashboard!

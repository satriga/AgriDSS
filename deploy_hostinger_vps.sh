#!/bin/bash
# ==============================================================================
# AgriDSS One-Click Deployment Script for Hostinger VPS (Ubuntu 22.04 / 24.04)
# ==============================================================================

set -e

echo "🚀 Starting AgriDSS Deployment on Hostinger VPS..."

# 1. Update OS & Install Python 3.11, Nginx, Git, build tools
echo "📦 Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv nginx git curl libgomp1

# 2. Setup project folder
APP_DIR="/var/www/agridss"
echo "📂 Setting up application directory at $APP_DIR..."
sudo mkdir -p $APP_DIR
sudo chown -R $USER:$USER $APP_DIR

# 3. Create Virtualenv & Install Python Packages
echo "🐍 Creating virtual environment..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Configure systemd service
echo "⚙️ Configuring systemd service..."
sudo cp agridss.service /etc/systemd/system/agridss.service
sudo systemctl daemon-reload
sudo systemctl enable agridss
sudo systemctl restart agridss

# 5. Configure Nginx
echo "🌐 Configuring Nginx reverse proxy..."
sudo cp nginx_agridss.conf /etc/nginx/sites-available/agridss
sudo ln -sf /etc/nginx/sites-available/agridss /etc/nginx/sites-enabled/agridss
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "✅ AgriDSS is successfully running!"
echo "👉 Check status with: sudo systemctl status agridss"
echo "👉 To setup free SSL (HTTPS): sudo apt install -y certbot python3-certbot-nginx && sudo certbot --nginx"

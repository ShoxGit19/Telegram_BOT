#!/bin/bash

cd /home/ec2-user/Telegram_BOT || exit

# O'zgarishlarni olish
git pull origin main --rebase

# Add
git add .

# Agar o'zgarish bo'lsa commit qiladi
git diff --cached --quiet || git commit -m "Auto save $(date)"

# Push
git push origin main

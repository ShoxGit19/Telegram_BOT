#!/bin/bash

cd /home/ec2-user/Telegram_BOT

git pull --rebase
git add .
git commit -m "Auto save" || true
git push

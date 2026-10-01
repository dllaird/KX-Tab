#!/usr/bin/env bash
# Certbot deploy hook: copy the renewed certificate where the kxtab user can read it, then restart.
#   sudo cp deploy/linux/certbot-deploy-hook.sh /etc/letsencrypt/renewal-hooks/deploy/kxtab.sh
#   sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/kxtab.sh
set -euo pipefail
dest=/etc/kxtab/tls
install -d -m 750 -o root -g kxtab "$dest"
install -m 640 -o root -g kxtab "$RENEWED_LINEAGE/fullchain.pem" "$dest/fullchain.pem"
install -m 640 -o root -g kxtab "$RENEWED_LINEAGE/privkey.pem" "$dest/privkey.pem"
systemctl restart kxtab-tabpy

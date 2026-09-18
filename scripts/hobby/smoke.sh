#!/usr/bin/env bash
# Live smoke test for the zero-cost hobby demo (docs/operations/hobby-deployment.md).
#
#   scripts/hobby/smoke.sh https://<web-host> https://<api-host>
#
# Registers a throwaway organisation with synthetic data, so run it only against
# the demo deployment — never against a production environment.
set -euo pipefail

WEB="${1:?kullanım: smoke.sh <web-url> <api-url>}"
API="${2:?kullanım: smoke.sh <web-url> <api-url>}"
WEB="${WEB%/}"
API="${API%/}"
SLUG="demo-$(date +%s)"
EMAIL="${SLUG}@ornek.example"
PASSWORD="DemoParola$(date +%s)!"
fail=0

step() { printf '\n== %s\n' "$1"; }
ok()   { printf '   OK   %s\n' "$1"; }
bad()  { printf '   FAIL %s\n' "$1"; fail=1; }

step "API hazırlık kontrolü (uykudan uyanma bir dakika sürebilir)"
for i in $(seq 1 30); do
  body=$(curl -fsS --max-time 30 "$API/health/ready" 2>/dev/null || true)
  [ -n "$body" ] && break
  sleep 5
done
case "${body:-}" in
  *'"status":"ok"'*) ok "/health/ready: $body" ;;
  *) bad "/health/ready yanıt vermedi: ${body:-<boş>}" ;;
esac

step "Web uygulaması"
code=$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 60 "$WEB/giris" || true)
[ "$code" = "200" ] && ok "GET $WEB/giris -> 200" || bad "GET $WEB/giris -> ${code:-hata}"

step "CORS kökeni yalnızca web adresine açık"
allow=$(curl -fsS -o /dev/null -D - --max-time 30 -X OPTIONS "$API/api/v1/auth/login" \
  -H "Origin: https://kotu-site.example" -H "Access-Control-Request-Method: POST" 2>/dev/null \
  | grep -i '^access-control-allow-origin' || true)
[ -z "$allow" ] && ok "yabancı köken için CORS başlığı yok" || bad "yabancı kökene izin veriliyor: $allow"

step "Kayıt (veritabanına yazma) ve giriş"
reg=$(curl -fsS --max-time 60 -X POST "$WEB/api/v1/auth/register" -H 'Content-Type: application/json' \
  -d "{\"organization_name\":\"Demo $SLUG\",\"slug\":\"$SLUG\",\"full_name\":\"Demo Kullanıcı\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" || true)
case "$reg" in
  *access_token*) ok "kayıt 201 (aynı köken üzerinden /api proxy'si çalışıyor)" ;;
  *) bad "kayıt başarısız: ${reg:0:200}" ;;
esac

login=$(curl -fsS --max-time 60 -X POST "$WEB/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" || true)
token=$(printf '%s' "$login" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null || true)
[ -n "$token" ] && ok "giriş başarılı" || bad "giriş başarısız: ${login:0:200}"

if [ -n "$token" ]; then
  step "Kimlikli uçlar (veritabanı okuma/yazma)"
  veh=$(curl -fsS --max-time 60 -X POST "$WEB/api/v1/vehicles" -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' -d '{"external_id":"34DEMO01","plate":"34 DEMO 01"}' || true)
  case "$veh" in *34DEMO01*) ok "araç oluşturuldu" ;; *) bad "araç oluşturulamadı: ${veh:0:200}" ;; esac
  sub=$(curl -fsS --max-time 60 "$WEB/api/v1/subscription" -H "Authorization: Bearer $token" || true)
  case "$sub" in *plan_key*) ok "abonelik okundu" ;; *) bad "abonelik okunamadı: ${sub:0:200}" ;; esac
fi

step "Hız sınırlama (Redis) yanıt başlıkları"
for _ in $(seq 1 12); do
  rl=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -X POST "$WEB/api/v1/auth/login" \
    -H 'Content-Type: application/json' -d '{"email":"yok@ornek.example","password":"YanlisParola1!"}' || true)
done
[ "$rl" = "429" ] && ok "tekrarlanan hatalı girişler 429 döndürüyor" || printf '   NOT  son durum %s (limitler yapılandırmaya göre değişir)\n' "$rl"

printf '\n'
[ "$fail" = "0" ] && echo "SONUÇ: canlı duman testi başarılı" || { echo "SONUÇ: canlı duman testinde hata var"; exit 1; }
echo "Not: doğrulama e-postası, kanıt yükleme ve canlı akış panelden elle denenmelidir."

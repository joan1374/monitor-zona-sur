import os, json, smtplib, requests, hashlib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
import time

EMAIL_REMITENTE = os.environ.get("EMAIL_REMITENTE", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_DESTINATARIO = os.environ.get("EMAIL_DESTINATARIO", "")
WA_PHONE = os.environ.get("WA_PHONE", "")
WA_APIKEY = os.environ.get("WA_APIKEY", "")
KEYWORDS = os.environ.get("KEYWORDS", "").split(",")

REGIONES = {
    "Arequipa": "04",
    "Moquegua": "15",
    "Cusco": "08",
    "Puno": "21",
    "Tacna": "23",
}
SEEN_FILE = "scripts/vistos.json"

def cargar_vistos():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def guardar_vistos(vistos):
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "w") as f:
        json.dump(list(vistos), f)

def id_conv(item):
    c = f"{item.get('numero','')}{item.get('objeto','')}{item.get('entidad','')}"
    return hashlib.md5(c.encode()).hexdigest()

def coincide(texto):
    if not any(k.strip() for k in KEYWORDS):
        return True
    return any(k.strip().lower() in texto.lower() for k in KEYWORDS if k.strip())

def obtener_seace():
    convs = []
    for region, cod in REGIONES.items():
        try:
            url = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico"
            payload = {
                "codigoDepartamento": cod,
                "estadoProceso": "ACT",
                "fechaInicio": (datetime.now() - timedelta(days=2)).strftime("%d/%m/%Y"),
                "fechaFin": datetime.now().strftime("%d/%m/%Y")
            }
            r = requests.post(url, data=payload, timeout=20, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Content-Type": "application/x-www-form-urlencoded"
            })
            soup = BeautifulSoup(r.text, "html.parser")
            for fila in soup.select("table tbody tr")[:20]:
                celdas = fila.find_all("td")
                if len(celdas) < 3: continue
                objeto = celdas[2].get_text(strip=True)
                if not coincide(objeto): continue
                convs.append({
                    "fuente": "SEACE",
                    "region": region,
                    "numero": celdas[0].get_text(strip=True),
                    "entidad": celdas[1].get_text(strip=True),
                    "objeto": objeto,
                    "monto": celdas[3].get_text(strip=True) if len(celdas) > 3 else "",
                    "fecha": celdas[4].get_text(strip=True) if len(celdas) > 4 else "",
                    "url": "https://seace.gob.pe"
                })
            time.sleep(1.5)
        except Exception as e:
            print(f"[SEACE {region}] {e}")
    return convs

def obtener_peru_compras():
    convs = []
    try:
        r = requests.get("https://www.perucompras.gob.pe/convocatorias/listarConvocatoriasVigentes.do", timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        for fila in soup.select("table tr")[1:40]:
            celdas = fila.find_all("td")
            if len(celdas) < 2: continue
            entidad = celdas[0].get_text(strip=True)
            objeto = celdas[1].get_text(strip=True)
            region = next((reg for reg in REGIONES if reg.lower() in entidad.lower()), None)
            if not region or not coincide(objeto): continue
            convs.append({
                "fuente": "Perú Compras",
                "region": region,
                "numero": celdas[2].get_text(strip=True) if len(celdas) > 2 else "",
                "entidad": entidad,
                "objeto": objeto,
                "monto": celdas[3].get_text(strip=True) if len(celdas) > 3 else "",
                "fecha": celdas[4].get_text(strip=True) if len(celdas) > 4 else "",
                "url": "https://www.perucompras.gob.pe"
            })
    except Exception as e:
        print(f"[PerúCompras] {e}")
    return convs

MINERAS = [
    {"nombre": "Southern Peru", "url": "https://www.southernperu.com/Proveedores/Convocatorias", "region": "Moquegua"},
    {"nombre": "Antapaccay", "url": "https://www.antapaccay.com.pe/proveedores", "region": "Cusco"},
    {"nombre": "Las Bambas", "url": "https://www.lasbambas.com/proveedores", "region": "Cusco"},
    {"nombre": "Cerro Verde", "url": "https://www.cerroverde.pe/proveedores/convocatorias", "region": "Arequipa"},
    {"nombre": "Minsur", "url": "https://www.minsur.com/proveedores", "region": "Puno"}
]

def obtener_mineras():
    convs = []
    for m in MINERAS:
        try:
            r = requests.get(m["url"], timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select(".convocatoria,.licitacion,.tender,article,.card")
            for item in items[:10]:
                texto = item.get_text(separator=" ", strip=True)
                if len(texto) < 10 or not coincide(texto): continue
                link = item.find("a")
                href = link["href"] if link and link.get("href") else m["url"]
                if href.startswith("/"):
                    from urllib.parse import urlparse
                    base = urlparse(m["url"])
                    href = f"{base.scheme}://{base.netloc}{href}"
                convs.append({
                    "fuente": m["nombre"],
                    "region": m["region"],
                    "numero": "",
                    "entidad": m["nombre"],
                    "objeto": texto[:200],
                    "monto": "",
                    "fecha": datetime.now().strftime("%d/%m/%Y"),
                    "url": href
                })
            time.sleep(1)
        except Exception as e:
            print(f"[{m['nombre']}] {e}")
    return convs

def enviar_email(nuevas):
    if not EMAIL_REMITENTE: return
    filas = "".join(
        f"<tr>"
        f"<td style='padding:8px;border-bottom:1px solid #eee'>{c['fuente']}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee'>{c['region']}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee'>{c['entidad']}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee'>{c['objeto'][:100]}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee'><a href='{c['url']}'>Ver</a></td>"
        f"</tr>" for c in nuevas
    )
    cuerpo = f"""<html><body style='font-family:Arial,sans-serif'>
    <div style='background:#185FA5;color:white;padding:20px;border-radius:8px 8px 0 0'>
    <h2>🔔 {len(nuevas)} nueva(s) convocatoria(s) — Zona Sur</h2>
    <p>{datetime.now().strftime('%d/%m/%Y %H:%M')}</p></div>
    <div style='border:1px solid #ddd;padding:20px'>
    <table style='width:100%;border-collapse:collapse;font-size:13px'>
    <thead style='background:#f5f5f5'><tr>
    <th style='padding:8px;text-align:left'>Fuente</th>
    <th style='padding:8px;text-align:left'>Región</th>
    <th style='padding:8px;text-align:left'>Entidad</th>
    <th style='padding:8px;text-align:left'>Objeto</th>
    <th style='padding:8px;text-align:left'>Link</th>
    </tr></thead><tbody>{filas}</tbody></table></div></body></html>"""
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 {len(nuevas)} convocatoria(s) Zona Sur — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    msg["From"] = EMAIL_REMITENTE
    msg["To"] = EMAIL_DESTINATARIO
    msg.attach(MIMEText(cuerpo, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_REMITENTE, EMAIL_PASSWORD)
            s.sendmail(EMAIL_REMITENTE, EMAIL_DESTINATARIO, msg.as_string())
        print(f"[Email] Enviado con éxito.")
    except Exception as e:
        print(f"[Email] Error: {e}")

def enviar_whatsapp(nuevas):
    if not WA_PHONE or WA_APIKEY == "0": 
        print("[WhatsApp] Saltado (No configurado aún).")
        return
    resumen = "\n".join(f"• {c['fuente']} | {c['region']}: {c['objeto'][:60]}..." for c in nuevas[:5])
    if len(nuevas) > 5: resumen += f"\n...y {len(nuevas)-5} más."
    msg = f"🔔 *{len(nuevas)} convocatoria(s) — Zona Sur*\n{datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n{resumen}"
    url = f"https://api.callmebot.com/whatsapp.php?phone={WA_PHONE}&text={requests.utils.quote(msg)}&apikey={WA_APIKEY}"
    try:
        r = requests.get(url, timeout=15)
        print(f"[WhatsApp] Enviado. Status: {r.status_code}")
    except Exception as e:
        print(f"[WhatsApp] Error: {e}")

def main():
    print(f"\nIniciando Monitor Zona Sur — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
    vistos = cargar_vistos()
    
    print("[1/3] Consultando SEACE...")
    seace = obtener_seace()
    print("[2/3] Consultando Perú Compras...")
    peru = obtener_peru_compras()
    print("[3/3] Consultando Páginas de Mineras...")
    minero = obtener_mineras()
    
    todas = seace + peru + minero
    nuevas = [c for c in todas if id_conv(c) not in vistos]
    print(f"\nResultados: {len(nuevas)} nuevas detectadas de {len(todas)} encontradas.")
    
    if nuevas:
        enviar_email(nuevas)
        enviar_whatsapp(nuevas)
        for c in nuevas: vistos.add(id_conv(c))
        guardar_vistos(vistos)
    
    os.makedirs("dashboard", exist_ok=True)
    with open("dashboard/data.json", "w", encoding="utf-8") as f:
        json.dump({"actualizado": datetime.now().isoformat(), "total": len(todas), "convocatorias": todas[-100:]}, f, ensure_ascii=False, indent=2)
    print("Proceso Finalizado.\n")

if __name__ == "__main__":
    main()

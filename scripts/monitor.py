import os, json, smtplib, requests, hashlib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
import time

EMAIL_REMITENTE    = os.environ.get("EMAIL_REMITENTE", "")
EMAIL_PASSWORD     = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_DESTINATARIO = os.environ.get("EMAIL_DESTINATARIO", "")
WA_PHONE           = os.environ.get("WA_PHONE", "")
WA_APIKEY          = os.environ.get("WA_APIKEY", "")
KEYWORDS           = os.environ.get("KEYWORDS", "").split(",")

DEPARTAMENTOS = {
    "Arequipa": "04",
    "Cusco":    "08",
    "Moquegua": "18",
    "Puno":     "21",
    "Tacna":    "23",
}

SEEN_FILE = "scripts/vistos.json"

def cargar_vistos():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def guardar_vistos(vistos):
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
    headers = {"User-Agent":"Mozilla/5.0","Content-Type":"application/x-www-form-urlencoded"}
    for depto, cod in DEPARTAMENTOS.items():
        try:
            url = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico"
            payload = {
                "codigoDepartamento": cod,
                "estadoProceso": "ACT",
                "fechaInicio": (datetime.now()-timedelta(days=3)).strftime("%d/%m/%Y"),
                "fechaFin": datetime.now().strftime("%d/%m/%Y"),
            }
            r = requests.post(url, data=payload, headers=headers, timeout=25)
            soup = BeautifulSoup(r.text, "html.parser")
            filas = soup.select("table tbody tr")
            print(f"  SEACE {depto}: {len(filas)} filas")
            for fila in filas[:30]:
                celdas = fila.find_all("td")
                if len(celdas) < 3:
                    continue
                objeto = celdas[2].get_text(strip=True)
                if not objeto or not coincide(objeto):
                    continue
                convs.append({
                    "fuente": "SEACE",
                    "region": depto,
                    "numero": celdas[0].get_text(strip=True),
                    "entidad": celdas[1].get_text(strip=True),
                    "objeto": objeto,
                    "monto": celdas[3].get_text(strip=True) if len(celdas) > 3 else "",
                    "fecha": celdas[4].get_text(strip=True) if len(celdas) > 4 else datetime.now().strftime("%d/%m/%Y"),
                    "url": "https://seace.gob.pe",
                })
            time.sleep(2)
        except Exception as e:
            print(f"  [SEACE {depto}] Error: {e}")
    return convs

def obtener_compras_menores():
    convs = []
    try:
        url = "https://comprasmenores.seace.gob.pe/Modulos/BancoPropuestas/ListarProcesos.aspx"
        r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        filas = soup.select("table tr")[1:50]
        print(f"  Compras Menores: {len(filas)} filas")
        for fila in filas:
            celdas = fila.find_all("td")
            if len(celdas) < 3:
                continue
            texto = " ".join(c.get_text(strip=True) for c in celdas)
            region = next((d for d in DEPARTAMENTOS if d.lower() in texto.lower()), None)
            if not region:
                continue
            objeto = celdas[2].get_text(strip=True)
            if not coincide(objeto):
                continue
            convs.append({
                "fuente": "Compras Menores",
                "region": region,
                "numero": celdas[0].get_text(strip=True),
                "entidad": celdas[1].get_text(strip=True),
                "objeto": objeto,
                "monto": celdas[3].get_text(strip=True) if len(celdas) > 3 else "",
                "fecha": celdas[4].get_text(strip=True) if len(celdas) > 4 else datetime.now().strftime("%d/%m/%Y"),
                "url": url,
            })
    except Exception as e:
        print(f"  [Compras Menores] Error: {e}")
    return convs

def obtener_peru_compras():
    convs = []
    try:
        url = "https://www.perucompras.gob.pe/convocatorias/listarConvocatoriasVigentes.do"
        r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        filas = soup.select("table tr")[1:50]
        print(f"  Peru Compras: {len(filas)} filas")
        for fila in filas:
            celdas = fila.find_all("td")
            if len(celdas) < 2:
                continue
            entidad = celdas[0].get_text(strip=True)
            objeto  = celdas[1].get_text(strip=True)
            region  = next((d for d in DEPARTAMENTOS if d.lower() in entidad.lower()), None)
            if not region or not coincide(objeto):
                continue
            convs.append({
                "fuente": "Peru Compras",
                "region": region,
                "numero": celdas[2].get_text(strip=True) if len(celdas) > 2 else "",
                "entidad": entidad,
                "objeto": objeto,
                "monto": celdas[3].get_text(strip=True) if len(celdas) > 3 else "",
                "fecha": celdas[4].get_text(strip=True) if len(celdas) > 4 else datetime.now().strftime("%d/%m/%Y"),
                "url": "https://www.perucompras.gob.pe",
            })
    except Exception as e:
        print(f"  [Peru Compras] Error: {e}")
    return convs

MINERAS = [
    {"nombre":"Southern Peru Copper","url":"https://www.southernperu.com/Proveedores/Convocatorias","region":"Moquegua"},
    {"nombre":"Antapaccay Glencore","url":"https://www.antapaccay.com.pe/proveedores","region":"Cusco"},
    {"nombre":"Las Bambas MMG","url":"https://www.lasbambas.com/proveedores","region":"Cusco"},
    {"nombre":"Cerro Verde Freeport","url":"https://www.cerroverde.pe/proveedores/convocatorias","region":"Arequipa"},
    {"nombre":"Minsur San Rafael","url":"https://www.minsur.com/proveedores","region":"Puno"},
    {"nombre":"Tia Maria Anglo American","url":"https://www.angloamerican.com/peru/proveedores","region":"Arequipa"},
    {"nombre":"Shougang Hierro Peru","url":"https://www.shougang.com.pe/proveedores","region":"Arequipa"},
    {"nombre":"Aruntani","url":"https://www.aruntani.com.pe/proveedores","region":"Puno"},
]

def obtener_mineras():
    convs = []
    for m in MINERAS:
        try:
            r = requests.get(m["url"], timeout=20, headers={"User-Agent":"Mozilla/5.0"})
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select(".convocatoria,.licitacion,.tender,.procurement,article,.card,.item")
            for item in items[:15]:
                texto = item.get_text(separator=" ", strip=True)
                if len(texto) < 15 or not coincide(texto):
                    continue
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
                    "url": href,
                })
            time.sleep(1)
        except Exception as e:
            print(f"  [{m['nombre']}] Error: {e}")
    return convs

def enviar_email(nuevas):
    if not EMAIL_REMITENTE:
        return
    filas = ""
    for c in nuevas:
        filas += (
            f"<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;font-size:12px'><b>{c['fuente']}</b></td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;font-size:12px'>{c['region']}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;font-size:12px'>{c['entidad']}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;font-size:12px'>{c['objeto'][:120]}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;font-size:12px'>{c.get('monto','')}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;font-size:12px'><a href='{c['url']}' style='color:#185FA5'>Ver</a></td>"
            f"</tr>"
        )
    cuerpo = (
        "<html><body style='font-family:Arial,sans-serif;max-width:900px;margin:auto'>"
        "<div style='background:#185FA5;color:white;padding:20px;border-radius:8px 8px 0 0'>"
        f"<h2 style='margin:0'>🔔 {len(nuevas)} nueva(s) convocatoria(s) Zona Sur</h2>"
        f"<p style='margin:6px 0 0;opacity:.85'>{datetime.now().strftime('%d/%m/%Y %H:%M')} | SEACE · Compras Menores · Peru Compras · Mineras</p>"
        "</div>"
        "<div style='border:1px solid #ddd;border-top:none;padding:16px;border-radius:0 0 8px 8px'>"
        "<table style='width:100%;border-collapse:collapse'>"
        "<thead style='background:#f5f5f5'><tr>"
        "<th style='padding:8px;text-align:left;font-size:12px'>Fuente</th>"
        "<th style='padding:8px;text-align:left;font-size:12px'>Region</th>"
        "<th style='padding:8px;text-align:left;font-size:12px'>Entidad</th>"
        "<th style='padding:8px;text-align:left;font-size:12px'>Objeto</th>"
        "<th style='padding:8px;text-align:left;font-size:12px'>Monto</th>"
        "<th style='padding:8px;text-align:left;font-size:12px'>Link</th>"
        f"</tr></thead><tbody>{filas}</tbody></table>"
        "<p style='font-size:11px;color:#999;margin-top:16px'>Monitor automatico Zona Sur del Peru</p>"
        "</div></body></html>"
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 {len(nuevas)} convocatoria(s) Zona Sur — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    msg["From"] = EMAIL_REMITENTE
    msg["To"]   = EMAIL_DESTINATARIO
    msg.attach(MIMEText(cuerpo, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_REMITENTE, EMAIL_PASSWORD)
            s.sendmail(EMAIL_REMITENTE, EMAIL_DESTINATARIO, msg.as_string())
        print(f"  [Email] Enviado — {len(nuevas)} convocatorias")
    except Exception as e:
        print(f"  [Email] Error: {e}")

def enviar_whatsapp(nuevas):
    if not WA_PHONE or not WA_APIKEY or WA_APIKEY == "0":
        return
    resumen = "\n".join(
        f"- {c['fuente']} | {c['region']}: {c['objeto'][:60]}..."
        for c in nuevas[:5]
    )
    if len(nuevas) > 5:
        resumen += f"\n...y {len(nuevas)-5} mas."
    msg = (
        f"🔔 {len(nuevas)} convocatoria(s) Zona Sur\n"
        f"{datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"{resumen}\n\nRevisa tu email para el detalle."
    )
    url = (
        f"https://api.callmebot.com/whatsapp.php"
        f"?phone={WA_PHONE}&text={requests.utils.quote(msg)}&apikey={WA_APIKEY}"
    )
    try:
        r = requests.get(url, timeout=15)
        print(f"  [WhatsApp] {'OK' if r.status_code==200 else 'Error '+str(r.status_code)}")
    except Exception as e:
        print(f"  [WhatsApp] Error: {e}")

def main():
    print("=" * 55)
    print(f"  Monitor Zona Sur — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 55)
    vistos = cargar_vistos()
    print(f"\n[1/4] SEACE — {len(DEPARTAMENTOS)} departamentos...")
    seace = obtener_seace()
    print(f"\n[2/4] Compras Menores del Estado...")
    menores = obtener_compras_menores()
    print(f"\n[3/4] Peru Compras...")
    peru = obtener_peru_compras()
    print(f"\n[4/4] Sector Minero — {len(MINERAS)} empresas...")
    minero = obtener_mineras()
    todas = seace + menores + peru + minero
    nuevas = [c for c in todas if id_conv(c) not in vistos]
    print(f"\n{'='*55}")
    print(f"  Consultadas: {len(todas)} | Nuevas: {len(nuevas)}")
    print(f"{'='*55}\n")
    if nuevas:
        enviar_email(nuevas)
        enviar_whatsapp(nuevas)
        for c in nuevas:
            vistos.add(id_conv(c))
        guardar_vistos(vistos)
    else:
        print("Sin convocatorias nuevas.")
    os.makedirs("dashboard", exist_ok=True)
    with open("dashboard/data.json", "w", encoding="utf-8") as f:
        json.dump({
            "actualizado": datetime.now().isoformat(),
            "total": len(todas),
            "convocatorias": todas[-200:]
        }, f, ensure_ascii=False, indent=2)
    print("Completado.\n")

if __name__ == "__main__":
    main()

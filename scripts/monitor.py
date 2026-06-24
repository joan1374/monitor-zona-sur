import os, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

EMAIL_REMITENTE    = os.environ.get("EMAIL_REMITENTE", "")
EMAIL_PASSWORD     = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_DESTINATARIO = os.environ.get("EMAIL_DESTINATARIO", "")

print(f"EMAIL_REMITENTE: {EMAIL_REMITENTE}")
print(f"EMAIL_DESTINATARIO: {EMAIL_DESTINATARIO}")
print(f"PASSWORD configurado: {'SI' if EMAIL_PASSWORD else 'NO'}")

if not EMAIL_REMITENTE:
    print("ERROR: EMAIL_REMITENTE vacío")
    exit(1)

print("Intentando enviar email de prueba...")

msg = MIMEMultipart("alternative")
msg["Subject"] = f"✅ Monitor Zona Sur - Prueba {datetime.now().strftime('%d/%m/%Y %H:%M')}"
msg["From"] = EMAIL_REMITENTE
msg["To"]   = EMAIL_DESTINATARIO
msg.attach(MIMEText("<h2>El monitor está funcionando correctamente.</h2>", "html"))

try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_REMITENTE, EMAIL_PASSWORD)
        s.sendmail(EMAIL_REMITENTE, EMAIL_DESTINATARIO, msg.as_string())
    print("EMAIL ENVIADO EXITOSAMENTE")
except Exception as e:
    print(f"ERROR al enviar email: {e}")

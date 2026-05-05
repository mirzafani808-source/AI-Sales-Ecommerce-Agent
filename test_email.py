import smtplib

smtp_server = "smtp.gmail.com"
port = 587
sender_email = "haidertafseer3@gmail.com"
password = "ycosnkdfirsmprtg"

server = smtplib.SMTP(smtp_server, port)
server.starttls()
server.login(sender_email, password)

message = "Subject: Test Email\n\nThis is a test email from AI Sales Agent."

server.sendmail(sender_email, sender_email, message)
server.quit()

print("Email sent successfully")
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import json
import threading
from app.database import get_db, release_db_connection

def email_base_template(title_text, title_color, body_content, footer_extra=''):
    """
    Template base HTML para todos os emails do sistema BiizHubOps.
    Tema claro, limpo, sem logo (logo já configurado no client de email).
    """
    return f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 640px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 10px; overflow: hidden; background-color: #ffffff;">
        <!-- Header -->
        <div style="background-color: {title_color}; padding: 18px 24px;">
            <span style="color: #ffffff; font-size: 20px; font-weight: 700; letter-spacing: 0.5px;">BiizHubOps</span>
            <span style="color: rgba(255,255,255,0.85); font-size: 14px; font-weight: 400; margin-left: 8px;">{title_text}</span>
        </div>
        <!-- Body -->
        <div style="padding: 24px; color: #333333; font-size: 14px; line-height: 1.7;">
            {body_content}
        </div>
        <!-- Footer -->
        <div style="background-color: #f5f5f5; padding: 14px 24px; text-align: center; border-top: 1px solid #e0e0e0;">
            {f'<p style="margin: 0 0 6px 0; color: #888; font-size: 11px;">{footer_extra}</p>' if footer_extra else ''}
            <p style="margin: 0; color: #999; font-size: 11px;">BiizHubOps DevOps &mdash; Orquestrador CI/CD &amp; Monitoramento para TOTVS Protheus</p>
        </div>
    </div>
    """

def get_notification_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notification_settings WHERE id = 1")
    settings = cursor.fetchone()
    release_db_connection(conn)
    return dict(settings) if settings else {}

def parse_template(template_str, context):
    """
    Substitui as variáveis {{chave}} na string template pelos valores do context.
    """
    if not template_str:
        return ""
        
    result = template_str
    for key, value in context.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result

def send_email_async(to_emails, subject, body_html, attachment=None):
    """
    Envia email de forma assíncrona
    attachment: tuple ('filename', b'content_bytes')
    """
    settings = get_notification_settings()
    if not settings or not settings.get('smtp_server') or not settings.get('smtp_port') or not settings.get('smtp_from_email'):
        return
        
    def _send():
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = settings['smtp_from_email']
            msg['To'] = ", ".join(to_emails)
            
            part = MIMEText(body_html, 'html')
            msg.attach(part)
            
            if attachment:
                from email.mime.application import MIMEApplication
                filename, content = attachment
                part_attach = MIMEApplication(content)
                part_attach.add_header('Content-Disposition', 'attachment', filename=filename)
                msg.attach(part_attach)
            
            port = settings['smtp_port']
            if port == 465:
                # SSL (Implicit)
                server = smtplib.SMTP_SSL(settings['smtp_server'], port)
            elif port == 587:
                # TLS (Explicit STARTTLS)
                server = smtplib.SMTP(settings['smtp_server'], port)
                server.starttls()
            else:
                server = smtplib.SMTP(settings['smtp_server'], port)
                
            if settings.get('smtp_user') and settings.get('smtp_password'):
                server.login(settings['smtp_user'], settings['smtp_password'])
                
            server.sendmail(settings['smtp_from_email'], to_emails, msg.as_string())
            server.quit()
        except Exception as e:
            print(f"[Notifier] Erro ao enviar email SMTP: {e}")

    threading.Thread(target=_send, daemon=True).start()

def send_whatsapp_async(to_numbers, context):
    """
    Envia WhatsApp via Webhook flexível em background.
    context deve conter pelo menos "message". "phone" será inserido no loop.
    """
    settings = get_notification_settings()
    if not settings or not settings.get('whatsapp_api_url'):
        return
        
    def _send():
        try:
            method = settings.get('whatsapp_api_method', 'POST').upper()
            url = settings['whatsapp_api_url']
            
            headers_raw = settings.get('whatsapp_api_headers', '{}')
            try:
                headers = json.loads(headers_raw)
            except:
                headers = {}
                
            body_template = settings.get('whatsapp_api_body', '{"number": "{{phone}}", "text": "{{message}}"}')
            
            for number in to_numbers:
                number_clean = ''.join(filter(str.isdigit, str(number)))
                if not number_clean:
                    continue
                    
                local_context = context.copy()
                local_context['phone'] = number_clean
                
                parsed_url = parse_template(url, local_context)
                parsed_body_str = parse_template(body_template, local_context)
                
                try:
                    payload = json.loads(parsed_body_str)
                    is_json = True
                except:
                    payload = parsed_body_str
                    is_json = False
                    
                if method == 'GET':
                    requests.get(parsed_url, headers=headers, timeout=10)
                else:
                    if is_json:
                        requests.request(method, parsed_url, headers=headers, json=payload, timeout=10)
                    else:
                        requests.request(method, parsed_url, headers=headers, data=payload, timeout=10)
                        
        except Exception as e:
            print(f"[Notifier] Erro ao enviar webhooks de whatsapp: {e}")

    threading.Thread(target=_send, daemon=True).start()

def _format_details_html(details_raw):
    try:
        if isinstance(details_raw, str):
            details = json.loads(details_raw)
        else:
            details = details_raw

        if isinstance(details, list):
            html_parts = []
            for item in details:
                is_success = item.get("success", False)
                bg_color = "#e8f5e9" if is_success else "#ffebee"
                border_color = "#4caf50" if is_success else "#f44336"
                text_color = "#2e7d32" if is_success else "#c62828"
                status_icon = "&#9989;" if is_success else "&#10060;"

                html_parts.append(f"""
                <div style="background-color: {bg_color}; color: #333; padding: 10px; margin-bottom: 10px; border-radius: 6px; border-left: 4px solid {border_color}; font-family: 'Courier New', monospace; font-size: 12px;">
                    <strong style="color: {text_color};">{status_icon} Serviço:</strong> {item.get('service', 'N/A')}<br>
                    <strong style="color: #555;">Servidor:</strong> {item.get('server', 'N/A')}<br>
                    <strong style="color: #555;">Método:</strong> {item.get('method', 'N/A')}<br>
                    <strong style="color: #555;">Saída:</strong><br>
                    <pre style="margin: 5px 0 0 0; white-space: pre-wrap; word-wrap: break-word; color: #444;">{item.get('output', 'N/A')}</pre>
                </div>
                """)
            return "".join(html_parts)
    except:
        pass

    return f'<pre style="background-color: #f5f5f5; padding: 10px; border-radius: 6px; color: #333; white-space: pre-wrap;">{details_raw}</pre>'

def _format_details_whatsapp(details_raw):
    try:
        if isinstance(details_raw, str):
            details = json.loads(details_raw)
        else:
            details = details_raw
            
        if isinstance(details, list):
            wa_parts = []
            for item in details:
                status_icon = "✅" if item.get("success", False) else "❌"
                wa_parts.append(f"{status_icon} *Serviço:* {item.get('service', 'N/A')}\n*Servidor:* {item.get('server', 'N/A')}\n*Saída:* {str(item.get('output', 'N/A')).strip()}")
            return "\n\n".join(wa_parts)
    except:
        pass
        
    return str(details_raw)

def send_pipeline_notification(pipeline_name, status, run_details, notify_emails=None, notify_whatsapp=None, log_text=None):
    if not notify_emails and not notify_whatsapp:
        return

    status_str = "SUCESSO" if status == 'success' else "FALHA"
    subject = f"[{status_str}] BiizHubOps: Pipeline '{pipeline_name}'"

    title_color = "#1b5e20" if status == 'success' else "#b71c1c"
    badge_bg = "#2e7d32" if status == 'success' else "#c62828"

    body_content = f"""
        <h3 style="color: #333; margin: 0 0 16px 0; border-bottom: 2px solid {badge_bg}; padding-bottom: 10px;">Pipeline: {pipeline_name}</h3>
        <table cellpadding="8" cellspacing="0" border="0" style="width: 100%;">
            <tr style="border-bottom: 1px solid #eee;">
                <td style="color: #666; width: 120px;">Status</td>
                <td><span style="background-color: {badge_bg}; color: #fff; padding: 4px 12px; border-radius: 4px; font-weight: 600; font-size: 13px;">{status_str}</span></td>
            </tr>
            <tr style="border-bottom: 1px solid #eee;">
                <td style="color: #666;">Início</td>
                <td style="color: #333;">{run_details.get('started_at', 'N/D')}</td>
            </tr>
            <tr>
                <td style="color: #666;">Fim</td>
                <td style="color: #333;">{run_details.get('finished_at', 'N/D')}</td>
            </tr>
        </table>
    """

    html_body = email_base_template('Pipeline', title_color, body_content)
    
    status_icon = "✅" if status == 'success' else "❌"
    wa_message = f"🚀 *BiizHubOps* | *Pipeline*\n*Nome:* {pipeline_name}\n*Status:* {status_icon} {status_str}"
    # Não quebrar JSON payload do WhatsApp enviando quebra de linhas problemáticas:
    wa_message = wa_message.replace('\n', '\\n') if getattr(get_notification_settings(), 'whatsapp_api_method', '') != 'GET' else wa_message
    context = {"message": wa_message, "pipeline_name": pipeline_name, "status": status_str}
    
    if notify_emails:
        emails_list = [e.strip() for e in notify_emails.split(',')]
        attachment = None
        if log_text:
            attachment = (f"pipeline_{pipeline_name}_log.txt", log_text.encode('utf-8'))
        send_email_async(emails_list, subject, html_body, attachment)
        
    if notify_whatsapp:
        whats_list = [w.strip() for w in notify_whatsapp.split(',')]
        send_whatsapp_async(whats_list, context)

def send_service_action_notification(action_name, status, details, notify_emails=None, notify_whatsapp=None):
    if not notify_emails and not notify_whatsapp:
        return

    status_str = status.upper()
    subject = f"[{status_str}] BiizHubOps: {action_name}"

    title_color = "#1b5e20" if status.lower() == 'success' else "#b71c1c"
    badge_bg = "#2e7d32" if status.lower() == 'success' else "#c62828"
    status_icon = "✅" if status.lower() == 'success' else "❌"

    formatted_html = _format_details_html(details)
    formatted_wa = _format_details_whatsapp(details)

    body_content = f"""
        <h3 style="color: #333; margin: 0 0 16px 0; border-bottom: 2px solid {badge_bg}; padding-bottom: 10px;">Comando: {action_name}</h3>
        <p style="margin: 0 0 16px 0;">
            <strong style="color: #666;">Status:</strong>
            <span style="background-color: {badge_bg}; color: #fff; padding: 4px 12px; border-radius: 4px; font-weight: 600; font-size: 13px;">{status_str}</span>
        </p>
        <h4 style="color: #555; margin: 16px 0 10px 0; font-size: 14px;">Detalhes da Execução:</h4>
        {formatted_html}
    """

    html_body = email_base_template('Comandos', title_color, body_content)
    
    wa_message = f"⚙️ *BiizHubOps* | *Service Action*\n*Nome:* {action_name}\n*Status:* {status_icon} {status_str}\n\n*Detalhes:*\n{formatted_wa}"
    wa_message = wa_message.replace('\n', '\\n') if getattr(get_notification_settings(), 'whatsapp_api_method', '') != 'GET' else wa_message
    
    context = {"message": wa_message, "action_name": action_name, "status": status_str}
    
    if notify_emails:
        emails_list = [e.strip() for e in notify_emails.split(',')]
        send_email_async(emails_list, subject, html_body)
        
    if notify_whatsapp:
        whats_list = [w.strip() for w in notify_whatsapp.split(',')]
        send_whatsapp_async(whats_list, context)

# -*- coding: utf-8 -*-
import csv
import io
import json
import logging
import math
from datetime import datetime

from odoo import http, fields
from odoo.http import request, content_disposition
import xlsxwriter

_logger = logging.getLogger(__name__)


def _user_allowed_days(u):
    days = []
    if u.send_on_monday:    days.append('Poniedziałek')
    if u.send_on_tuesday:   days.append('Wtorek')
    if u.send_on_wednesday: days.append('Środa')
    if u.send_on_thursday:  days.append('Czwartek')
    if u.send_on_friday:    days.append('Piątek')
    if u.send_on_saturday:  days.append('Sobota')
    if u.send_on_sunday:    days.append('Niedziela')
    return days


def _sender_numbers_for_user(u):
    # zwraca [(value, label), ...]
    return [(rec.number, rec.number) for rec in (u.sender_number_ids or u.env['sms.user_sender_number'])]


class SmsCampaignPortal(http.Controller):

    # --- Helper: upewnij się, że kampania należy do zalogowanego użytkownika ---
    def _ensure_owner_or_404(self, campaign_id: int):
        campaign = request.env['sms.campaign'].sudo().browse(int(campaign_id))
        if not campaign.exists() or campaign.user_id.id != request.env.user.id:
            return None
        return campaign

    # ---------------------------------------------
    # Lista kampanii (tylko moje)
    # ---------------------------------------------
    @http.route(['/my/sms_campaigns'], type='http', auth='user', website=True)
    def portal_my_sms_campaigns(self, search=None, status=None, view='grid',
                                group_by=None, date_from=None, date_to=None, page=1, **kw):
        """
        Renderuje listę kampanii SMS z paginacją i filtrami (tylko kampanie zalogowanego użytkownika)
        """
        uid = request.env.user.id
        Campaign = request.env['sms.campaign'].sudo()
        domain = [('user_id', '=', uid)]

        # Filtry
        if search:
            domain.append(('name', 'ilike', search))
        if status:
            domain.append(('state', '=', status))
        if date_from:
            domain.append(('date_start', '>=', date_from))
        if date_to:
            domain.append(('date_start', '<=', date_to))

        # Paginacja
        page_size = 20
        page = int(page or 1)
        total_campaigns = Campaign.search_count(domain)
        campaigns = Campaign.search(
            domain,
            limit=page_size,
            offset=(page - 1) * page_size,
            order='date_start desc, id desc'
        )

        # Statystyki (po tym samym domain)
        def _sum(field):
            recs = Campaign.search(domain)
            return sum(getattr(c, field, 0) or 0 for c in recs)

        stats = {
            'stats_total_campaigns': total_campaigns,
            'stats_total_messages': _sum('message_count'),
            'stats_total_sent': _sum('sent_count'),
            'stats_total_delivered': _sum('delivered_count'),
            'stats_total_failed': _sum('failed_count'),
        }

        u = request.env.user  # bez sudo: czytamy z profilu zalogowanego
        allowed_days = _user_allowed_days(u)
        hours_from = u.hours_from or 0.0
        hours_to = u.hours_to or 0.0

        return request.render('odoo17_sms_plugin.sms_campaigns_list_page', {
            'my_campaigns': campaigns,
            'search':       search,
            'status':       status,
            'view':         view,
            'group_by':     group_by,
            'date_from':    date_from,
            'date_to':      date_to,
            'page':         page,
            'page_size':    page_size,
            'page_count':   math.ceil(total_campaigns / page_size),
            'total_campaigns': total_campaigns,
            'allowed_days': allowed_days,
            'hours_from': hours_from,
            'hours_to': hours_to,
            **stats,
        })

    # ---------------------------------------------
    # Szczegóły kampanii (tylko moja)
    # ---------------------------------------------
    @http.route(['/my/sms_campaigns/<int:campaign_id>'], type='http', auth='user', website=True)
    def portal_sms_campaign_detail(self, campaign_id, page=1, **kw):
        """
        Renderuje szczegóły kampanii z paginacją wiadomości (widoczne tylko dla właściciela)
        """
        campaign = self._ensure_owner_or_404(campaign_id)
        if not campaign:
            return request.not_found()

        # Paginacja wiadomości (dodatkowo filtrujemy po user_id aby nie pokazać cudzych)
        page_size = 20
        page = int(page or 1)
        Message = request.env['sms.message'].sudo()
        domain = [('campaign_id', '=', campaign.id), ('user_id', '=', request.env.user.id)]
        total_messages = Message.search_count(domain)
        messages = Message.search(domain, offset=(page - 1) * page_size, limit=page_size, order='date_scheduled desc')
        page_count = math.ceil(total_messages / page_size)

        # Dane do wykresu
        labels = ['Oczekujące', 'Zaplanowane', 'Wysłane', 'Dostarczone', 'Nieudane']
        states = ['draft', 'scheduled', 'sent', 'delivered', 'failed']
        values = [Message.search_count([('campaign_id', '=', campaign.id), ('state', '=', st), ('user_id', '=', request.env.user.id)]) for st in states]

        return request.render('odoo17_sms_plugin.sms_campaign_detail_page', {
            'campaign': campaign.sudo(),
            'campaign_id': campaign_id,
            'messages': messages,
            'message_count': len(messages),
            'total_messages': total_messages,
            'page': page,
            'page_size': page_size,
            'page_count': page_count,
            'back_url': '/my/sms_campaigns',
            'chart_labels_json': json.dumps(labels, ensure_ascii=False),
            'chart_values_json': json.dumps(values, ensure_ascii=False),
        })

    # ---------------------------------------------
    # Edycja kampanii (GET) – tylko moja
    # ---------------------------------------------
    @http.route(['/my/sms_campaigns/<int:campaign_id>/edit'], type='http', auth='user', website=True)
    def portal_sms_campaign_edit(self, campaign_id, **kw):
        campaign = self._ensure_owner_or_404(campaign_id)
        if not campaign:
            return request.not_found()
        warning = request.session.pop('portal_warning', False)
        sender_numbers = _sender_numbers_for_user(request.env.user)  # numery zalogowanego usera
        return request.render('odoo17_sms_plugin.sms_campaign_edit_page', {
            'campaign': campaign.sudo(),
            'portal_warning': warning,
            'sender_numbers': sender_numbers,
        })

    # ---------------------------------------------
    # Edycja kampanii (POST update) – tylko moja
    # ---------------------------------------------
    @http.route(['/my/sms_campaigns/<int:campaign_id>/update'], type='http', methods=['POST'], auth='user', website=True)
    def portal_sms_campaign_update(self, campaign_id, **post):
        campaign = self._ensure_owner_or_404(campaign_id)
        if not campaign:
            return request.not_found()

        # Przygotowanie wartości
        vals = {
            'name': (post.get('name') or '').strip(),
            'single_message': (post.get('single_message') or '').strip(),
            'sender_number': (post.get('sender_number') or '').strip(),
        }
        # Usuń puste, żeby nie nadpisywać None
        vals = {k: v for k, v in vals.items() if v}

        raw_start = post.get('date_start')
        if raw_start:
            try:
                dt = datetime.strptime(raw_start, '%Y-%m-%dT%H:%M')
                vals['date_start'] = dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass

            # Walidacja
            message = request.env['sms.campaign'].sudo()._check_date_start_logic(vals.get('date_start'))
            if message:
                request.session['portal_warning'] = message
                return request.redirect(f'/my/sms_campaigns/{campaign.id}/edit')

        # Zapis
        if vals:
            campaign.sudo().write(vals)
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    # ---------------------------------------------
    # Nowa kampania (GET)
    # ---------------------------------------------
    @http.route(['/my/sms_campaigns/new'], type='http', auth='user', website=True)
    def portal_sms_campaign_new(self, **kw):
        warning = request.session.pop('portal_warning', False)
        sender_numbers = _sender_numbers_for_user(request.env.user)
        u = request.env.user
        return request.render('odoo17_sms_plugin.sms_campaign_new_page', {
            'portal_warning': warning,
            'sender_numbers': sender_numbers,
            'allowed_days': _user_allowed_days(u),
            'hours_from': u.hours_from or 0.0,
            'hours_to': u.hours_to or 0.0,
        })

    # ---------------------------------------------
    # Nowa kampania (POST) – ustawia ownera
    # ---------------------------------------------
    @http.route(['/my/sms_campaigns/new'], type='http', methods=['POST'], auth='user', website=True)
    def portal_sms_campaign_create(self, **post):
        name = (post.get('name') or '').strip()
        single_message = (post.get('single_message') or '').strip()
        sender_number = (post.get('sender_number') or '').strip()
        raw_start = post.get('date_start')

        if not (name and single_message and sender_number and raw_start):
            request.session['portal_warning'] = "Brak wymaganych pól."
            return request.redirect('/my/sms_campaigns/new')

        try:
            dt = datetime.strptime(raw_start, '%Y-%m-%dT%H:%M')
            date_start = dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            date_start = False

        # Walidacja daty
        message = request.env['sms.campaign'].sudo()._check_date_start_logic(date_start)
        if message:
            request.session['portal_warning'] = message
            return request.redirect('/my/sms_campaigns/new')

        # Tworzenie kampanii z ownerem
        vals = {
            'name': name,
            'state': 'draft',
            'single_message': single_message,
            'sender_number': sender_number,
            'date_start': date_start,
            'user_id': request.env.user.id,  # właściciel
        }
        campaign = request.env['sms.campaign'].sudo().create(vals)

        csv_file = post.get('csv_file')
        if csv_file:
            try:
                data = csv_file.read().decode('utf-8')
                reader = csv.DictReader(io.StringIO(data))
                Partner = request.env['res.partner'].sudo()
                created = 0
                limit = 10  # spójnie z wersją demo uploadu

                for row in reader:
                    if created >= limit:
                        break

                    phone = (row.get('phone') or row.get('phone_number') or
                             row.get('numer') or row.get('numer_telefonu') or
                             row.get('numer_odbiorcy') or '').strip()
                    if not phone:
                        continue

                    # NOWE: per-wierszowa treść z kolumny 'message' (fallback do treści kampanii)
                    msg_body = (row.get('message') or campaign.single_message or '').strip()

                    partner = Partner.search([('phone', '=', phone)], limit=1)
                    if not partner:
                        partner = Partner.create({'name': phone, 'phone': phone})

                    request.env['sms.message'].sudo().create({
                        'campaign_id': campaign.id,
                        'partner_id': partner.id,
                        'body': msg_body,
                        'state': 'draft',
                        'sender_number': campaign.sender_number,
                        'user_id': request.env.user.id,
                    })
                    created += 1

                request.session['portal_success'] = f"Zaimportowano {created} rekordów z CSV (limit {limit})."
            except Exception as e:
                _logger.exception("Błąd importu CSV przy tworzeniu kampanii")
                request.session['portal_warning'] = f"Błąd importu CSV: {e}"

        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    # ---------------------------------------------
    # Start/Stop/Retry – tylko moje
    # ---------------------------------------------
    @http.route(['/my/sms_campaigns/<int:campaign_id>/start'], type='http', auth='user', website=True)
    def portal_sms_campaign_start(self, campaign_id, **kw):
        campaign = self._ensure_owner_or_404(campaign_id)
        if not campaign:
            return request.not_found()
        campaign.sudo().action_start()
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    @http.route(['/my/sms_campaigns/<int:campaign_id>/stop'], type='http', auth='user', website=True)
    def portal_sms_campaign_stop(self, campaign_id, **kw):
        campaign = self._ensure_owner_or_404(campaign_id)
        if not campaign:
            return request.not_found()
        if campaign.state == 'running':
            campaign.sudo().write({'state': 'done', 'date_end': fields.Datetime.now()})
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    @http.route(['/my/sms_campaigns/<int:campaign_id>/retry'], type='http', auth='user', website=True)
    def portal_sms_campaign_retry(self, campaign_id, **kw):
        campaign = self._ensure_owner_or_404(campaign_id)
        if not campaign:
            return request.not_found()
        if campaign.state == 'done':
            campaign.sudo().write({'state': 'draft'})
            failed_messages = campaign.message_ids.filtered(lambda m: m.state == 'failed' and m.user_id.id == request.env.user.id)
            for msg in failed_messages:
                msg.sudo().write({'state': 'draft'})
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    @http.route(['/my/sms_campaigns/<int:campaign_id>/retry_all'], type='http', auth='user', website=True)
    def portal_sms_campaign_retry_all(self, campaign_id, **kw):
        """
        REST-only: polling odpowiedzi + odświeżenie statusów w kontekście zalogowanego usera.
        """
        campaign = self._ensure_owner_or_404(campaign_id)
        if not campaign:
            return request.not_found()

        # Wywołaj polling W KONTEKŚCIE zalogowanego usera (jego poświadczenia API)
        request.env['sms.message'].with_user(request.env.user).poll_delivery_status()
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    # ---------------------------------------------
    # Wyczyść wiadomości kampanii – tylko moja
    # ---------------------------------------------
    @http.route(['/my/sms_campaigns/<int:campaign_id>/clear_numbers'], type='http', methods=['POST'], auth='user', website=True)
    def portal_sms_campaign_clear_numbers(self, campaign_id, **post):
        campaign = self._ensure_owner_or_404(campaign_id)
        if not campaign:
            return request.not_found()
        # Usuń tylko wiadomości należące do tej kampanii (pośrednio do usera – bo kampania jego)
        campaign.message_ids.sudo().unlink()
        return request.redirect(f'/my/sms_campaigns/{campaign.id}/edit')

    # ---------------------------------------------
    # Import CSV (limit 10) – tylko moja
    # ---------------------------------------------
    @http.route(['/my/sms_campaigns/<int:campaign_id>/upload_csv'], type='http', auth='user', methods=['POST'],
                website=True)
    def portal_sms_campaign_upload_csv(self, campaign_id, **post):
        campaign = self._ensure_owner_or_404(campaign_id)
        if not campaign or campaign.state != 'draft':
            return request.not_found()

        csv_file = post.get('csv_file')
        if not csv_file:
            return request.redirect(f"/my/sms_campaigns/{campaign.id}")

        try:
            data = csv_file.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(data))

            Partner = request.env['res.partner'].sudo()
            created = 0
            limit = 10

            for row in reader:
                if created >= limit:
                    _logger.info("Osiągnięto limit %s rekordów – pozostałe wiersze zostały pominięte", limit)
                    break

                # Uczyń klucze nagłówków nieczułe na wielkość liter
                row_ci = {(k or '').strip().lower(): (v or '').strip() for k, v in (row or {}).items()}

                phone = (
                        row_ci.get('phone')
                        or row_ci.get('phone_number')
                        or row_ci.get('numer')
                        or row_ci.get('numer_telefonu')
                        or row_ci.get('numer_odbiorcy')
                        or ''
                ).strip()
                if not phone:
                    continue

                # NOWE: per-wierszowa treść z kolumny 'message' (jeśli podana), inaczej treść z kampanii
                body_text = (row_ci.get('message') or '').strip() or (campaign.single_message or '').strip()
                if not body_text:
                    continue

                partner = Partner.search([('phone', '=', phone)], limit=1)
                if not partner:
                    partner = Partner.create({'name': phone, 'phone': phone})

                request.env['sms.message'].sudo().create({
                    'campaign_id': campaign.id,
                    'partner_id': partner.id,
                    'body': body_text,  # <-- kluczowa zmiana
                    'state': 'draft',
                    'sender_number': campaign.sender_number,
                    'user_id': request.env.user.id,
                })
                created += 1

            request.session['portal_success'] = f"Zaimportowano {created} wiadomości (limit {limit})."
        except Exception as e:
            _logger.exception("Błąd importu CSV")
            request.session['portal_warning'] = f"Błąd importu: {e}"

        return request.redirect(f"/my/sms_campaigns/{campaign.id}")

    # ---------------------------------------------
    # Eksport do Excel – tylko moja
    # ---------------------------------------------
    @http.route(['/my/sms_campaigns/<int:campaign_id>/export_excel'], type='http', auth='user', website=True)
    def portal_sms_campaign_export_excel(self, campaign_id, **kw):
        campaign = self._ensure_owner_or_404(campaign_id)
        if not campaign:
            return request.not_found()

        messages = campaign.message_ids

        # Przygotowanie pliku XLSX w pamięci
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet("Raport SMS")

        # Style
        title_format = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter'})
        stat_label_format = workbook.add_format({'bold': True, 'bg_color': '#DCE6F1', 'border': 1})
        stat_value_format = workbook.add_format({'border': 1})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#4F81BD', 'font_color': 'white', 'border': 1})
        row_format_1 = workbook.add_format({'border': 1, 'bg_color': '#FFFFFF'})
        row_format_2 = workbook.add_format({'border': 1, 'bg_color': '#F2F2F2'})

        # Tytuł
        sheet.merge_range('A1:H1',
                          f"Raport SMS dla - {campaign.name} z dnia {campaign.date_start.strftime('%Y-%m-%d %H:%M:%S') if campaign.date_start else ''}",
                          title_format)

        # Statystyki
        stats_rows = [
            ['Wiadomości ogółem', campaign.message_count],
            ['Wysłane', campaign.sent_count],
            ['Dostarczone', campaign.delivered_count],
            ['Nieudane', campaign.failed_count],
            ['Wskaźnik dostarczenia (%)', f"{campaign.delivery_rate:.2f}" if getattr(campaign, 'delivery_rate', None) is not None else ''],
        ]
        stat_row_start = 2
        for r, (label, value) in enumerate(stats_rows, start=stat_row_start):
            sheet.write(r, 0, label, stat_label_format)
            sheet.write(r, 1, value, stat_value_format)

        # Tabela
        start_row = stat_row_start + len(stats_rows) + 2
        headers = ['Lp.', 'Numer odbiorcy', 'Treść wiadomości', 'Ilość znaków', 'Ilość wiadomości', 'Status', 'Odpowiedź bramki', 'Ilość prób wysyłki']
        for col, title in enumerate(headers):
            sheet.write(start_row, col, title, header_format)

        for idx, msg in enumerate(messages, start=1):
            row = start_row + idx
            fmt = row_format_1 if (idx % 2) else row_format_2
            sheet.write(row, 0, idx, fmt)
            sheet.write(row, 1, msg.partner_id.phone or '', fmt)
            sheet.write(row, 2, msg.body or '', fmt)
            sheet.write(row, 3, msg.char_count or '', fmt)
            sheet.write(row, 4, msg.sms_message_count or '', fmt)
            sheet.write(row, 5, msg.state or '', fmt)
            sheet.write(row, 6, msg.sms_gateway_response_human or '', fmt)
            sheet.write(row, 7, msg.sms_reply_number or '', fmt)

        for col in range(len(headers)):
            sheet.set_column(col, col, 20)

        workbook.close()
        output.seek(0)
        data = output.read()

        filename = f"Raport_{campaign.name}_z_dnia_{campaign.date_start.strftime('%Y-%m-%d %H:%M:%S') if campaign.date_start else ''}.xlsx"
        return request.make_response(
            data,
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(filename)),
            ]
        )

    # ---------------------------------------------
    # Wyślij raport e-mailem – tylko moja
    # ---------------------------------------------
    @http.route(['/my/sms_campaigns/<int:campaign_id>/send_report_email'], type='http', auth='user', website=True)
    def portal_sms_campaign_send_report_email(self, campaign_id, **kw):
        campaign = self._ensure_owner_or_404(campaign_id)
        if not campaign:
            return request.not_found()

        try:
            campaign.sudo().send_excel_report_by_email()
            request.session['portal_success'] = f"Raport kampanii '{campaign.name}' został wysłany na e-mail."
        except Exception as e:
            _logger.exception("Błąd wysyłki raportu dla kampanii %s", campaign.name)
            request.session['portal_warning'] = f"Błąd wysyłki raportu: {str(e)}"

        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

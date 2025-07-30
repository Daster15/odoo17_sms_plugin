# -*- coding: utf-8 -*-
import math

from odoo import http, fields
from odoo.http import request
from datetime import datetime
import csv
import io
import logging
import xlsxwriter
import math, json
from odoo.http import request, content_disposition

_logger = logging.getLogger(__name__)


class SmsCampaignPortal(http.Controller):

    @http.route(['/my/sms_campaigns'], type='http', auth='user', website=True)
    def portal_my_sms_campaigns(self, search=None, status=None, view='grid',
                                group_by=None, date_from=None, date_to=None, page=1, **kw):
        """
        Renderuje listę kampanii SMS z paginacją i filtrami
        """
        Campaign = request.env['sms.campaign'].sudo()
        domain = []

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
        page = int(page)
        total_campaigns = Campaign.search_count(domain)
        campaigns = Campaign.search(domain,
                                    limit=page_size,
                                    offset=(page - 1) * page_size,
                                    order='date_start desc')
        page_count = (total_campaigns + page_size - 1) // page_size

        user = request.env.user.sudo()
        send_days = [
            ('Poniedziałek', user.send_on_monday),
            ('Wtorek', user.send_on_tuesday),
            ('Środa', user.send_on_wednesday),
            ('Czwartek', user.send_on_thursday),
            ('Piątek', user.send_on_friday),
            ('Sobota', user.send_on_saturday),
            ('Niedziela', user.send_on_sunday),
        ]
        allowed_days = [label for label, is_active in send_days if is_active]
        hours_from = user.hours_from
        hours_to = user.hours_to

        stats = {
            'stats_total_campaigns': total_campaigns,
            'stats_total_messages': sum(c.message_count or 0 for c in Campaign.search(domain)),
            'stats_total_sent': sum(c.sent_count or 0 for c in Campaign.search(domain)),
            'stats_total_delivered': sum(c.delivered_count or 0 for c in Campaign.search(domain)),
            'stats_total_failed': sum(c.failed_count or 0 for c in Campaign.search(domain)),
        }

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
            # dodatkowo zostawiamy total_campaigns, ale statystyki biorą się z stats_*
            'total_campaigns': total_campaigns,
            'allowed_days': allowed_days,
            'hours_from': hours_from,
            'hours_to': hours_to,
            **stats,
        })

    @http.route(['/my/sms_campaigns/<int:campaign_id>'], type='http', auth='user', website=True)
    def portal_sms_campaign_detail(self, campaign_id, page=1, **kw):
        """
        Renderuje szczegóły kampanii z paginacją wiadomości
        """
        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        if not campaign.exists():
            return request.not_found()

        # Paginacja wiadomości
        page_size = 20
        page = int(page)
        total_messages = len(campaign.message_ids)
        messages = campaign.message_ids[(page - 1) * page_size: page * page_size]
        page_count = (total_messages + page_size - 1) // page_size
        domain = [('campaign_id', '=', campaign.id)]
        Message = request.env['sms.message']
        messages = Message.search(domain, offset=(page - 1) * page_size, limit=page_size, order='date_scheduled desc')

        # Przygotuj dane do wykresu
        labels = ['Oczekujące', 'Zaplanowane', 'Wysłane', 'Dostarczone', 'Nieudane']
        states = ['draft', 'scheduled', 'sent', 'delivered', 'failed']
        values = [len(campaign.message_ids.filtered(lambda m: m.state == st))
                  for st in states]

        return request.render('odoo17_sms_plugin.sms_campaign_detail_page', {
            'campaign': campaign,
            'messages': messages,
            'message_count': len(messages),
            'total_messages': total_messages,
            'page': page,
            'page_size': page_size,
            'page_count': page_count,
            'back_url': '/my/sms_campaigns',
            'chart_labels_json': json.dumps(labels),
            'chart_values_json': json.dumps(values),
        })

    @http.route(['/my/sms_campaigns/<int:campaign_id>/edit'], type='http', auth='user', website=True)
    def portal_sms_campaign_edit(self, campaign_id, **kw):
        """Renderuje formularz edycji kampanii"""
        _logger.info("edycja 222222222222222!!!!!!!!!!!!!!!!!!")
        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        warning = request.session.pop('portal_warning', False)
        if not campaign.exists():
            return request.not_found()
        sender_numbers = request.env['sms.campaign'].sudo()._get_available_campaning_sender_numbers()
        return request.render('odoo17_sms_plugin.sms_campaign_edit_page', {
            'campaign': campaign,
            'portal_warning': warning,
            'sender_numbers': sender_numbers,
     })

    @http.route(['/my/sms_campaigns/<int:campaign_id>/update'], type='http', methods=['POST'], auth='user',
                website=True)
    def portal_sms_campaign_update(self, campaign_id, **post):
        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        if not campaign:
            return request.not_found()
        # Przygotowanie wartości
        vals = {
            'name': post.get('name'),
            'single_message': post.get('single_message'),
            'sender_number': post.get('sender_number'),
        }
        raw_start = post.get('date_start')
        if raw_start:
            dt = datetime.strptime(raw_start, '%Y-%m-%dT%H:%M')
            vals['date_start'] = dt.strftime('%Y-%m-%d %H:%M:%S')
            # Walidacja
            message = request.env['sms.campaign'].sudo()._check_date_start_logic(vals['date_start'])
            if message:
                request.session['portal_warning'] = message
                return request.redirect(f'/my/sms_campaigns/{campaign.id}/edit')
        # Zapis
        campaign.write(vals)
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    @http.route(['/my/sms_campaigns/new'], type='http', auth='user', website=True)
    def portal_sms_campaign_new(self, **kw):
        """Renderuje formularz tworzenia nowej kampanii"""
        sender_numbers = request.env['sms.campaign'].sudo()._get_available_campaning_sender_numbers()
        warning = request.session.pop('portal_warning', False)
        return request.render('odoo17_sms_plugin.sms_campaign_new_page', {
            'portal_warning': warning,
            'sender_numbers': sender_numbers,
        })

    @http.route(['/my/sms_campaigns/new'], type='http', methods=['POST'], auth='user', website=True)
    def portal_sms_campaign_create(self, **post):
        # Przygotowanie wartości
        vals = {
            'name': post.get('name'),
            'state': 'draft',
            'single_message': post.get('single_message'),
            'sender_number': post.get('sender_number'),
        }
        raw_start = post.get('date_start')
        if raw_start:
            # Parsowanie z formatu HTML5 datetime-local
            dt = datetime.strptime(raw_start, '%Y-%m-%dT%H:%M')
            vals['date_start'] = dt.strftime('%Y-%m-%d %H:%M:%S')
            # Walidacja przy użyciu modelu
            message = request.env['sms.campaign'].sudo()._check_date_start_logic(vals['date_start'])
            if message:
                request.session['portal_warning'] = message
                return request.redirect('/my/sms_campaigns/new')
        # Tworzenie kampanii
        campaign = request.env['sms.campaign'].sudo().create(vals)
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    @http.route(['/my/sms_campaigns/<int:campaign_id>/start'], type='http', auth='user', website=True)
    def portal_sms_campaign_start(self, campaign_id, **kw):
        """Uruchamia kampanię SMS w modelu (wysyła, zapisuje external_id i kończy)."""
        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        if not campaign:
            return request.not_found()
        # Cała logika wysyłki i zamykania kampanii jest w modelu:
        campaign.action_start()
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    @http.route([
        '/my/sms_campaigns/<int:campaign_id>/clear_numbers'
    ], type='http', methods=['POST'], auth='user', website=True)
    def portal_sms_campaign_clear_numbers(self, campaign_id, **post):
        """Usuwa wszystkie zaimportowane numery (wiadomości) z kampanii."""
        _logger.info('usuwanie rekodrow')
        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        if not campaign.exists():
            return request.not_found()
        # usuwamy wszystkie powiązane sms.message
        campaign.message_ids.sudo().unlink()
        # powrót do edycji kampanii
        return request.redirect(f'/my/sms_campaigns/{campaign.id}/edit')

    @http.route(['/my/sms_campaigns/<int:campaign_id>/stop'], type='http', auth='user', website=True)
    def portal_sms_campaign_stop(self, campaign_id, **kw):
        """Zatrzymuje kampanię SMS"""
        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        if campaign.state == 'running':
            campaign.write({'state': 'done'})
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    @http.route(['/my/sms_campaigns/<int:campaign_id>/retry'], type='http', auth='user', website=True)
    def portal_sms_campaign_retry(self, campaign_id, **kw):
        """Ponawia próbę wysłania nieudanych wiadomości"""
        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        if campaign.state == 'done':
            campaign.write({'state': 'draft'})
            failed_messages = campaign.message_ids.filtered(
                lambda m: m.state == 'failed'
            )
            for msg in failed_messages:
                msg.write({'state': 'draft'})
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    @http.route(['/my/sms_campaigns/<int:campaign_id>/retry_all'], type='http', auth='user', website=True)
    def portal_sms_campaign_retry_all(self, campaign_id, **kw):
        """
        Odświeża statusy wszystkich SMS-ów w kampanii i przekierowuje z powrotem na detail.
        """
        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        if not campaign.exists():
            return request.not_found()
        # wczytanie i zaktualizowanie statusów (poll) wszystkich wiadomości
        # wykorzystujemy już istniejącą metodę modelu:
        request.env['sms.message'].sudo().poll_delivery_status()
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    @http.route(['/my/sms_campaigns/<int:campaign_id>/upload_csv'],
                type='http', auth='user', methods=['POST'], website=True)
    def portal_sms_campaign_upload_csv(self, campaign_id, **post):
        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        if not campaign.exists() or campaign.state != 'draft':
            return request.not_found()

        csv_file = post.get('csv_file')
        if not csv_file:
            return request.redirect(f"/my/sms_campaigns/{campaign.id}")

        try:
            data = csv_file.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(data))

            Partner = request.env['res.partner'].sudo()
            created = 0
            limit = 10  # maksymalna liczba rekordów do zaimportowania

            for row in reader:
                if created >= limit:
                    _logger.info("Osiągnięto limit %s rekordów – pozostałe wiersze zostały pominięte", limit)
                    break

                phone = (row.get('phone') or row.get('phone_number') or '').strip()
                if not phone:
                    continue

                partner = Partner.search([('phone', '=', phone)], limit=1)
                if not partner:
                    partner = Partner.create({
                        'name': phone,
                        'phone': phone,
                    })

                request.env['sms.message'].sudo().create({
                    'campaign_id': campaign.id,
                    'partner_id': partner.id,
                    'body': campaign.single_message,
                    'state': 'draft',
                })
                created += 1

            request.session['portal_success'] = f"Zaimportowano {created} wiadomości (limit {limit})"
        except Exception as e:
            request.session['portal_warning'] = f"Błąd importu: {e}"

        return request.redirect(f"/my/sms_campaigns/{campaign.id}")

    def _build_list_url(self, **kw):
        """Pomocnicza metoda do budowania URL listy z parametrami"""
        params = {
            'view': kw.get('view', 'grid'),
            'search': kw.get('search', ''),
            'status': kw.get('status', ''),
            'group_by': kw.get('group_by', ''),
            'date_from': kw.get('date_from', ''),
            'date_to': kw.get('date_to', ''),
            'page': kw.get('page', 1)
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items() if v)
        return f"/my/sms_campaigns?{qs}"

    @http.route([
        '/my/sms_campaigns/<int:campaign_id>/export_excel'
    ], type='http', auth='user', website=True)
    def portal_sms_campaign_export_excel(self, campaign_id, **kw):
        # Pobierz kampanię
        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        if not campaign.exists():
            return request.not_found()

        # Filtrujemy tylko wysłane SMS-y
        messages = campaign.message_ids.filtered(lambda m: m.state == 'sent')

        # Przygotowanie pliku XLSX w pamięci
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet("Wysłane SMS")

        # Nagłówki
        headers = [
            'Lp.', 'Data zaplanowana', 'Numer odbiorcy', 'Treść wiadomości',
            'External ID', 'Odpowiedź bramki', 'Status'
        ]
        for col, title in enumerate(headers):
            sheet.write(0, col, title)

        # Wypełniamy wiersze danymi
        for row, msg in enumerate(messages, start=1):
            sheet.write(row, 0, row)
            # date_scheduled to datetime lub False
            sheet.write(row, 1, msg.date_scheduled.strftime('%Y-%m-%d %H:%M:%S')
            if msg.date_scheduled else '')
            sheet.write(row, 2, msg.partner_id.phone or '')
            sheet.write(row, 3, msg.body or '')
            sheet.write(row, 4, msg.external_id or '')
            sheet.write(row, 5, msg.sms_gateway_response or '')
            sheet.write(row, 6, msg.sms_gateway_response_human or '')
            sheet.write(row, 7, msg.state)

        workbook.close()
        output.seek(0)
        data = output.read()

        # Przygotowanie odpowiedzi HTTP z załącznikiem
        filename = f"sms_campaign_{campaign.id}_messages.xlsx"
        return request.make_response(
            data,
            headers=[
                ('Content-Type',
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(filename))
            ]
        )

    @http.route(['/my/sms_campaigns/<int:campaign_id>/send_report_email'],
                type='http', auth='user', website=True)
    def portal_sms_campaign_send_report_email(self, campaign_id, **kw):
        """
        Wysyła raport XLSX kampanii na e-mail ustawiony w stats_email użytkownika.
        """
        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        if not campaign.exists():
            return request.not_found()

        try:
            campaign.send_excel_report_by_email()
            request.session['portal_success'] = f"Raport kampanii '{campaign.name}' został wysłany na e-mail."
        except Exception as e:
            _logger.exception("Błąd wysyłki raportu dla kampanii %s", campaign.name)
            request.session['portal_warning'] = f"Błąd wysyłki raportu: {str(e)}"

        # Po wysyłce przekierowanie z powrotem do szczegółów kampanii
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')
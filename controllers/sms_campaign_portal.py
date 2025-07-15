# -*- coding: utf-8 -*-
import math

from odoo import http, fields
from odoo.http import request
from datetime import datetime
import csv
import io
import logging

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

        # Statystyki
        #stats = {
        #    'total_campaigns': total_campaigns,
        #    'total_messages': sum(c.message_count or 0 for c in Campaign.search(domain)),
        #    'total_sent': sum(c.sent_count or 0 for c in Campaign.search(domain)),
         #   'total_delivered': sum(c.delivered_count or 0 for c in Campaign.search(domain)),
        #    'total_failed': sum(c.failed_count or 0 for c in Campaign.search(domain))
        #}
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

        return request.render('odoo17_sms_plugin.sms_campaign_detail_page', {
            'campaign': campaign,
            'messages': messages,
            'message_count': len(messages),
            'total_messages': total_messages,
            'page': page,
            'page_size': page_size,
            'page_count': page_count,
            'back_url': '/my/sms_campaigns'
        })

    @http.route(['/my/sms_campaigns/<int:campaign_id>/edit'], type='http', auth='user', website=True)
    def portal_sms_campaign_edit(self, campaign_id, **kw):
        """Renderuje formularz edycji kampanii"""
        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        if not campaign.exists():
            return request.not_found()
        sender_numbers = request.env['sms.campaign'].sudo()._get_available_campaning_sender_numbers()
        return request.render('odoo17_sms_plugin.sms_campaign_edit_page', {
            'campaign': campaign,
            'sender_numbers': sender_numbers,
     })

    @http.route(['/my/sms_campaigns/<int:campaign_id>/edit'], type='http', methods=['POST'], auth='user', website=True)
    def portal_sms_campaign_update(self, campaign_id, **post):
        _logger.info("edycja !!!!!!!!!!!!!!!!!!")
        raw_start = post.get('date_start')
        raw_end = post.get('date_end')
        vals = {
            'name': post.get('name'),
            'single_message': post.get('single_message'),
            'sender_number': post.get('sender_number'),
        }
        if raw_start:
            dt = datetime.strptime(raw_start, '%Y-%m-%dT%H:%M')
            vals['date_start'] = dt.strftime('%Y-%m-%d %H:%M:%S')
        if raw_end:
            dt = datetime.strptime(raw_end, '%Y-%m-%dT%H:%M')
            vals['date_end'] = dt.strftime('%Y-%m-%d %H:%M:%S')
        else:
            vals['date_end'] = False

        campaign = request.env['sms.campaign'].sudo().browse(campaign_id)
        campaign.write(vals)
        return request.redirect(f'/my/sms_campaigns/{campaign.id}')

    @http.route(['/my/sms_campaigns/new'], type='http', auth='user', website=True)
    def portal_sms_campaign_new(self, **kw):
        """Renderuje formularz tworzenia nowej kampanii"""
        sender_numbers = request.env['sms.campaign'].sudo()._get_available_campaning_sender_numbers()
        return request.render('odoo17_sms_plugin.sms_campaign_new_page', {
            'sender_numbers': sender_numbers,
        })

    @http.route(['/my/sms_campaigns/new'], type='http', methods=['POST'], auth='user', website=True)
    def portal_sms_campaign_create(self, **post):
        # parsowanie dat
        raw_start = post.get('date_start')
        raw_end = post.get('date_end')
        vals = {
            'name': post.get('name'),
            'state': 'draft',
            'single_message': post.get('single_message'),
            # pobieramy WYBRANĄ wartość, nie całą listę
            'sender_number': post.get('sender_number'),
        }
        if raw_start:
            dt = datetime.strptime(raw_start, '%Y-%m-%dT%H:%M')
            vals['date_start'] = dt.strftime('%Y-%m-%d %H:%M:%S')
        if raw_end:
            dt = datetime.strptime(raw_end, '%Y-%m-%dT%H:%M')
            vals['date_end'] = dt.strftime('%Y-%m-%d %H:%M:%S')
        else:
            vals['date_end'] = False

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
            for row in reader:
                phone = (row.get('phone') or row.get('phone_number') or '').strip()
                # wymagamy tylko numeru
                if not phone:
                    continue

                partner = Partner.search([('phone', '=', phone)], limit=1)
                if not partner:
                    partner = Partner.create({
                        'name': phone,
                        'phone': phone,
                    })

                # treść zawsze z pola single_message kampanii
                request.env['sms.message'].sudo().create({
                    'campaign_id': campaign.id,
                    'partner_id': partner.id,
                    'body': campaign.single_message,
                    'state': 'draft',
                })
                created += 1

            request.session['portal_success'] = f"Zaimportowano {created} wiadomości"
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
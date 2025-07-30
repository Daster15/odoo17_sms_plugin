

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import base64
import io
import xlsxwriter

_logger = logging.getLogger(__name__)


class SmsCampaign(models.Model):
    _name = 'sms.campaign'
    _description = 'SMS Campaign'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Campaign Name', required=True, tracking=True)
    message_ids = fields.One2many('sms.message', 'campaign_id', string='Messages')
    date_start = fields.Datetime(string='Start Date')
    date_end = fields.Datetime(string='End Date')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('verify', 'Verify'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    #single_message = fields.Boolean(string='Single Message')
    single_message = fields.Text(string = 'Treść wiadomości',required = True,help = 'Wiadomość, która zostanie wysłana do każdego odbiorcy')

    sender_number = fields.Selection(
        selection='_get_available_campaning_sender_numbers',
        string='Sender Number',
        required=True,
        default=lambda self: self._get_available_campaning_sender_numbers()
    )

    report_sent = fields.Boolean(string='Raport wysłany', default=False)

    def _get_available_campaning_sender_numbers(self):
        """Zwraca listę dostępnych numerów nadawcy"""
        return [
            ('+48123456789', 'CLIP (POXBOX)'),
            ('+48987654321', 'Marketing (+48 600 100 100)'),
            ('+48111222333111111111', 'Support (+48 600 200 21100)')
        ]


    # Pola statystyczne

    pending_count = fields.Integer(
        string='Pending',
        compute='_compute_stats',
        store=True,
    )

    message_count = fields.Integer(
        string='Total Messages',
        compute='_compute_stats',
        store=True
    )
    sent_count = fields.Integer(
        string='Sent Messages',
        compute='_compute_stats',
        store=True
    )
    delivered_count = fields.Integer(
        string='Delivered',
        compute='_compute_stats',
        store=True
    )
    failed_count = fields.Integer(
        string='Failed',
        compute='_compute_stats',
        store=True
    )
    delivery_rate = fields.Float(
        string='Delivery Rate (%)',
        compute='_compute_stats',
        store=True,
        group_operator="avg"
    )
    scheduled_count = fields.Integer(
        string='Scheduled',
        compute='_compute_stats',
        store=True
    )

    def _check_date_start_logic(self, date_start_str):
        """
        Przyjmuje date_start w formacie 'YYYY-MM-DD HH:MM:SS' (UTC),
        zwraca None jeśli data jest OK, albo string z komunikatem o błędzie.
        """
        if not date_start_str:
            return
        # Konwersja string → datetime → UTC → local user tz
        dt = fields.Datetime.from_string(date_start_str)
        local_dt = fields.Datetime.context_timestamp(self, dt)
        user = self.env.user
        # Mapowanie dni tygodnia
        day_map = {
            0: ('send_on_monday', 'Poniedziałek'),
            1: ('send_on_tuesday', 'Wtorek'),
            2: ('send_on_wednesday', 'Środa'),
            3: ('send_on_thursday', 'Czwartek'),
            4: ('send_on_friday', 'Piątek'),
            5: ('send_on_saturday', 'Sobota'),
            6: ('send_on_sunday', 'Niedziela'),
        }
        field_name, day_name = day_map[local_dt.weekday()]
        if not getattr(user, field_name):
            return f"Data rozpoczęcia ({local_dt.strftime('%Y-%m-%d %H:%M')}) przypada w {day_name}, w którym wysyłka jest wyłączona."
        # Sprawdzenie godziny
        hour = local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0
        if hour < user.hours_from or hour > user.hours_to:
            fh, fm = divmod(int(user.hours_from * 60), 60)
            th, tm = divmod(int(user.hours_to * 60), 60)
            return (
                f"Godzina rozpoczęcia ({local_dt.strftime('%H:%M')}) musi być między "
                f"{fh:02d}:{fm:02d} a {th:02d}:{tm:02d}."
            )
        # OK
        return

    @api.constrains('date_start')
    def _check_date_start_with_user_settings(self):
        """
        Sprawdza, czy date_start kampanii mieści się w ustawieniach
        dnia tygodnia i godzin użytkownika.
        """
        for rec in self:
            if not rec.date_start:
                continue
            user = rec.env.user
            # Konwertujemy do strefy czasowej użytkownika
            local_dt = fields.Datetime.context_timestamp(rec, rec.date_start)
            wday = local_dt.weekday()  # 0=Poniedziałek, 6=Niedziela
            day_map = {
                0: ('send_on_monday', 'Poniedziałek'),
                1: ('send_on_tuesday', 'Wtorek'),
                2: ('send_on_wednesday', 'Środa'),
                3: ('send_on_thursday', 'Czwartek'),
                4: ('send_on_friday', 'Piątek'),
                5: ('send_on_saturday', 'Sobota'),
                6: ('send_on_sunday', 'Niedziela'),
            }
            field_name, day_name = day_map[wday]
            # Sprawdzenie dnia tygodnia
            if not getattr(user, field_name):
                raise UserError(f"Data rozpoczęcia przypada w {day_name}, w którym wysyłka SMS jest wyłączona.")
            # Sprawdzenie godziny
            hour_decimal = local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0
            from_hour = user.hours_from
            to_hour = user.hours_to
            if hour_decimal < from_hour or hour_decimal > to_hour:
                # Formatuj godziny użytkownika
                from_h = int(from_hour)
                from_m = int((from_hour - from_h) * 60)
                to_h = int(to_hour)
                to_m = int((to_hour - to_h) * 60)
                raise UserError(
                    f"Godzina rozpoczęcia kampanii ({local_dt.strftime('%H:%M')}) "
                    f"musi być pomiędzy {from_h:02d}:{from_m:02d} a {to_h:02d}:{to_m:02d} "
                    f"zgodnie z ustawieniami użytkownika."
                )

    @api.depends('message_ids', 'message_ids.state', 'message_ids.sms_gateway_response')
    def _compute_stats(self):
        for campaign in self:
            messages = campaign.message_ids
            # Ile w ogóle wiadomości
            campaign.message_count = len(messages)

            # Wysłane: stan 'sent' lub 'delivered'
            campaign.sent_count = len(
                messages.filtered(lambda m: m.state in ('sent', 'delivered'))
            )

            # Dostarczone: na podstawie sms_gateway_response
            def _is_delivered(m):
                if not m.sms_gateway_response:
                    return False
                txt = m.sms_gateway_response.lower()
                return 'zakończona sukcesem' in txt or 'potwierdziło wysyłkę' in txt

            campaign.delivered_count = len(
                messages.filtered(_is_delivered)
            )

            # Nieudane
            campaign.failed_count = len(
                messages.filtered(lambda m: m.state == 'failed')
            )

            # Zaplanowane
            campaign.scheduled_count = len(
                messages.filtered(lambda m: m.state == 'scheduled')
            )

            # % dostarczeń
            if campaign.message_count:
                campaign.delivery_rate = (
                    campaign.delivered_count / campaign.message_count * 100.0
                )
            else:
                campaign.delivery_rate = 0.0

    def send_excel_report_by_email(self):
        """Wysyła raport kampanii jako załącznik XLSX na e-mail z ustawień użytkownika SMS."""
        for campaign in self:
            user = self.env.user
            if not user.stats_email:
                _logger.warning("Brak adresu stats_email dla użytkownika %s", user.name)
                continue

            # Pobierz wiadomości z kampanii
            messages = campaign.message_ids.filtered(lambda m: m.state in ('sent', 'delivered', 'failed'))

            # Stwórz plik Excel w pamięci
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet("Raport")

            headers = ['Lp.', 'Numer odbiorcy', 'Treść wiadomości','Ilość znaków', 'External ID', 'Status',
                       'Odpowiedź bramki','Ilość prób wysyłki']
            for col, title in enumerate(headers):
                sheet.write(0, col, title)

            for row, msg in enumerate(messages, start=1):
                sheet.write(row, 0, row)
                sheet.write(row, 1, msg.partner_id.phone or '')
                sheet.write(row, 2, msg.body or '')
                sheet.write(row, 3, msg.char_count or '')
                sheet.write(row, 4, msg.external_id or '')
                sheet.write(row, 5, msg.state or '')
                sheet.write(row, 6, msg.sms_gateway_response_human or '')
                sheet.write(row, 7, msg.sms_reply_number or '')

            workbook.close()
            output.seek(0)
            attachment_data = output.read()

            # Załącznik do maila
            attachment = self.env['ir.attachment'].create({
                'name': f'Raport_{campaign.name}.xlsx',
                'type': 'binary',
                'datas': base64.b64encode(attachment_data),
                'res_model': 'sms.campaign',
                'res_id': campaign.id,
                'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            })

            # Szablon HTML wiadomości
            body_html = f"""
                    <table style="width:100%;max-width:600px;margin:auto;font-family:Arial,sans-serif;border-collapse:collapse;">
                      <tr>
                        <td style="background:#2c7be5;color:white;padding:16px;font-size:20px;font-weight:bold;">
                          📊 Raport kampanii SMS – <span style="color:#ffdd57;">{campaign.name}</span>
                        </td>
                      </tr>
                      <tr>
                        <td style="background:#f9f9f9;padding:20px;">
                          <p style="font-size:15px;color:#333;">
                            Dzień dobry,<br><br>
                            Poniżej znajduje się podsumowanie kampanii <b>{campaign.name}</b>.
                            Pełny raport znajdziesz w załączniku w formacie Excel.
                          </p>

                          <table style="width:100%;border-collapse:collapse;margin-top:15px;">
                            <tr>
                              <td style="border:1px solid #ddd;padding:8px;background:#f1f1f1;">📅 Data rozpoczęcia</td>
                              <td style="border:1px solid #ddd;padding:8px;">{campaign.date_start.strftime('%Y-%m-%d %H:%M:%S') if campaign.date_start else '-'}</td>
                            </tr>
                            <tr>
                              <td style="border:1px solid #ddd;padding:8px;background:#f1f1f1;">📅 Data zakończenia</td>
                              <td style="border:1px solid #ddd;padding:8px;">{campaign.date_end.strftime('%Y-%m-%d %H:%M:%S') if campaign.date_end else '-'}</td>
                            </tr>
                            <tr>
                              <td style="border:1px solid #ddd;padding:8px;background:#f1f1f1;">✉️ Wysłane wiadomości</td>
                              <td style="border:1px solid #ddd;padding:8px;">{campaign.sent_count}</td>
                            </tr>
                            <tr>
                              <td style="border:1px solid #ddd;padding:8px;background:#f1f1f1;">📬 Dostarczone</td>
                              <td style="border:1px solid #ddd;padding:8px;color:green;font-weight:bold;">{campaign.delivered_count}</td>
                            </tr>
                            <tr>
                              <td style="border:1px solid #ddd;padding:8px;background:#f1f1f1;">⚠️ Niedostarczone</td>
                              <td style="border:1px solid #ddd;padding:8px;color:red;font-weight:bold;">{campaign.failed_count}</td>
                            </tr>
                            <tr>
                              <td style="border:1px solid #ddd;padding:8px;background:#f1f1f1;">📈 Wskaźnik dostarczenia</td>
                              <td style="border:1px solid #ddd;padding:8px;">{round(campaign.delivery_rate or 0, 2)}%</td>
                            </tr>
                          </table>

                          <p style="font-size:14px;color:#777;margin-top:15px;">
                            📎 Załącznik: Raport kampanii w formacie XLSX<br>
                            🔍 W raporcie znajdziesz listę wszystkich numerów odbiorców, treści wiadomości oraz statusy dostarczenia.
                          </p>
                        </td>
                      </tr>
                      <tr>
                        <td style="background:#2c7be5;color:white;text-align:center;padding:10px;font-size:12px;">
                          System kampanii SMS | Wygenerowano automatycznie przez PoxBox
                        </td>
                      </tr>
                    </table>
                    """

            # Wysyłka maila
            self.env['mail.mail'].create({
                'subject': f'Raport kampanii SMS: {campaign.name}',
                'body_html': body_html,
                'email_to': user.stats_email,
                'email_from': 'smsrapo@poxbox.pl' or 'no-reply@example.com',
                'attachment_ids': [(6, 0, [attachment.id])],
            }).send()

    def action_start(self):
        """Uruchamia kampanię, wysyła wszystkie wiadomości i kończy kampanię."""
        now = fields.Datetime.now()
        for campaign in self:
            if campaign.state != 'draft':
                continue
            # 1) Zmiana stanu i data startu
            campaign.write({
                'state': 'running',
                'date_start': now,
            })
            # 2) Wysyłka SMS-ów
            to_send = campaign.message_ids.filtered(
                lambda m: m.state in ('draft', 'scheduled')
            )
            to_send.action_send_now()
            # 3) Jeżeli wszystkie są już wysłane/dostarczone, kończymy kampanię
            if campaign.message_ids and all(
                m.state in ('sent', 'delivered') for m in campaign.message_ids
            ):
                campaign.write({
                    'state': 'running',
                    'date_end': fields.Datetime.now(),
                })
                campaign.message_ids.poll_delivery_status()

        return True

    def action_stop(self):
        self.write({
            'state': 'done',
            'date_end': fields.Datetime.now()
        })
        # po zakończeniu kampanii ponawiamy wszystkie nie-sent SMS-y
        for camp in self:
            unsent = camp.message_ids.filtered(lambda m: m.state != 'sent')
            if unsent:
                _logger.info(
                    "Kampania %s: ponawiam wysyłkę %s wiadomości",
                    camp.name, len(unsent)
                )
                unsent.action_send_now()

    def action_cancel(self):
        self.write({
            'state': 'cancelled',
            'date_end': fields.Datetime.now()
        })
        # opcjonalnie: przy anulowaniu też retry
        for camp in self:
            unsent = camp.message_ids.filtered(lambda m: m.state != 'sent')
            if unsent:
                _logger.info(
                    "Kampania %s (anulowana): ponawiam wysyłkę %s wiadomości",
                    camp.name, len(unsent)
                )
                unsent.action_send_now()

    def action_retry_failed(self):
        failed_messages = self.message_ids.filtered(lambda m: m.state == 'failed')
        if failed_messages:
            failed_messages.action_send_now()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Retry Started"),
                    'message': _("%d failed messages are being retried") % len(failed_messages),
                    'type': 'success',
                }
            }
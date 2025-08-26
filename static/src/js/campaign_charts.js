/** @odoo-module **/
import { Chart } from "web.assets_frontend";

export function mountCampaignChart(stats) {
  const ctx = document.getElementById("campaignChart");
  if (!ctx) return;

  new Chart(ctx, {
    type: "bar",
    data: {
      labels: ["Wysłane", "Dostarczone", "Nieudane"],
      datasets: [
        {
          label: "SMS-y",
          data: [
            stats.total_sent,
            stats.total_delivered,
            stats.total_failed,
          ],
          backgroundColor: ["#0d6efd", "#198754", "#dc3545"],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true },
      },
    },
  });
}

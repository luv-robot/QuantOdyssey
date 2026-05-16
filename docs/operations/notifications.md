# Notifications

QuantOdyssey uses n8n for human-facing approvals and notifications.

## Current n8n Workflow

The starter workflow is `QuantOdyssey Research Thesis Intake`.

Webhook:

```text
POST http://45.32.44.245:5678/webhook/research-thesis
```

Production webhook:

```text
POST https://quantodyssey.com/webhook/research-thesis
X-QuantOdyssey-Webhook-Secret: <server secret>
Authorization: Basic <dashboard credentials>
```

The production route requires both Basic Auth and `X-QuantOdyssey-Webhook-Secret`.
The secret is stored only on the VPS in `.env` as `N8N_WEBHOOK_SECRET`.

Payload example:

```json
{
  "title": "Volume continuation after absorption",
  "market_observation": "BTC breaks range on high volume but spread stays tight.",
  "hypothesis": "Absorption plus volume expansion improves continuation odds.",
  "trade_logic": "Enter after shallow pullback if liquidity remains healthy."
}
```

The current workflow returns a `mailto:luweiword@gmail.com` link. Fully automatic email
delivery requires SMTP, Gmail, SendGrid, AWS SES, or another provider credential inside n8n.

## Supervisor System Alerts

The workflow `QuantOdyssey Supervisor System Alert` receives system-level Supervisor alerts:

```text
POST http://n8n:5678/webhook/supervisor-system-alert
```

External production route:

```text
POST https://quantodyssey.com/webhook/supervisor-system-alert
X-QuantOdyssey-Webhook-Secret: <server secret>
Authorization: Basic <dashboard credentials>
```

Payloads include:

```json
{
  "type": "supervisor_system_alert",
  "status": "critical",
  "summary": "Supervisor status is critical...",
  "notify": {
    "user_email": "luweiword@gmail.com",
    "dev_agent_channel": "dashboard_supervisor_inbox"
  },
  "dev_agent_handoff": {
    "priority": "critical",
    "instruction": "Inspect the latest SupervisorReport..."
  }
}
```

By default this workflow returns a `mailto:` link and structured developer-agent handoff. Add SMTP,
Telegram, or Feishu nodes after the code node when you want true push notifications.

## Telegram

Recommended path:

1. Open Telegram and message `@BotFather`.
2. Run `/newbot` and create a bot.
3. Copy the bot token.
4. Start a chat with the bot, then get your chat id via:

```bash
curl "https://api.telegram.org/bot<token>/getUpdates"
```

5. In n8n, add a Telegram credential with the bot token.
6. Add a Telegram node after the webhook/code node and send messages to your chat id.

## Feishu

Yes, Feishu can be connected. The simplest option is a Feishu custom bot webhook:

1. Create or choose a Feishu group.
2. Add a custom bot.
3. Copy the webhook URL.
4. In n8n, add an HTTP Request node.
5. POST JSON to the Feishu webhook.

Typical text payload:

```json
{
  "msg_type": "text",
  "content": {
    "text": "QuantOdyssey notification"
  }
}
```

If you need interactive approvals, use a Feishu app with bot permissions and callback URLs
instead of only a custom webhook.

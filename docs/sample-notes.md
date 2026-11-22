# Sample notes for trying "Draft backlog"

Synthetic text, safe to paste into the Agent console (it is sent to Gemini). Copy everything inside the box.

```
Planning call, 24 Nov (synthetic example, not real project data).

Support is getting about twenty tickets a week from customers who cannot find their invoices. Customers should be able to download any past invoice as a PDF from their account page. The PDF must show the invoice number, date, line items and total.

Finance wants a weekly email summary of overdue invoices, sent every Monday morning to the finance team. It only needs to list invoices that are more than 14 days overdue. Nobody decided who maintains the recipient list.

Customers keep asking to change the email address on their account. They should be able to do it themselves, and we must send a confirmation link to the new address before the change takes effect. The link should expire after 24 hours.

The admin team asked for a log of who changed customer billing details, with the date and the old and new value. Admins only need to read it; nobody can edit or delete entries.

Someone suggested a mobile app, and someone else suggested a chatbot for support. Nothing was agreed on either, so leave them for now.
```

## What a good run does

- Drafts about four items: invoice PDF download, the weekly overdue-invoice email, self-service email change with a
  confirmation link, and the billing-change log.
- Leaves out the mobile app and the chatbot, because nobody committed to them.
- Flags assumptions to check, for example who maintains the overdue-email recipient list.
- Cites a passage of the notes for every draft; on the review page each quote is highlighted in the original text.

## To see a guardrail refuse something

Add this line before the last paragraph. If your project already has an open issue with that exact title, the
duplicate rule refuses the draft and says so:

```
We also need to add an OAuth login flow so customers can sign in with Google and GitHub.
```

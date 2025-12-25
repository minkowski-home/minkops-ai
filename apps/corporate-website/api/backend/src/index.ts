import express from "express";

const PORT = Number(process.env.PORT ?? 5000);
const HOST = process.env.HOST ?? "0.0.0.0";

const app = express();

app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "corporate-website" });
});

app.listen(PORT, HOST, () => {
  console.log(`[corporate-website] API listening on http://${HOST}:${PORT}`);
});

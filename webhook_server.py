"""Flask webhook sharing the bot's handlers and one persistent event loop."""
import asyncio
import atexit
import os
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError
from flask import Flask, request
from telegram import Update
from first import build_application, logger


def create_app(application=None):
    application = application or build_application()
    flask_app = Flask(__name__)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, name="telegram-webhook", daemon=True)
    thread.start()
    initialized = False
    initialization_lock = asyncio.Lock()

    async def enqueue(payload):
        nonlocal initialized
        async with initialization_lock:
            if not initialized:
                await application.initialize()
                await application.start()
                initialized = True
        update = Update.de_json(payload, application.bot)
        await application.update_queue.put(update)

    @flask_app.post("/webhook")
    def webhook():
        secret = os.getenv("WEBHOOK_SECRET")
        if secret and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
            return "forbidden", 403
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("update_id"), int):
            return "invalid update", 400
        future = asyncio.run_coroutine_threadsafe(enqueue(payload), loop)
        try:
            future.result(timeout=30)
        except FutureTimeoutError:
            future.cancel()
            return "temporarily unavailable", 503
        except Exception:
            logger.exception("Webhook xabarini qabul qilishda xatolik")
            return "temporarily unavailable", 503
        return "ok", 200

    async def stop():
        if initialized:
            await application.stop()
            await application.shutdown()

    def close():
        if loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(stop(), loop).result(timeout=10)
            finally:
                loop.call_soon_threadsafe(loop.stop)
                thread.join(timeout=10)
                if not thread.is_alive():
                    loop.close()

    atexit.register(close)
    flask_app.extensions["telegram_application"] = application
    flask_app.extensions["telegram_shutdown"] = close
    return flask_app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("PORT", "8443")))

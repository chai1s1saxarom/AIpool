import httpx
import asyncio
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict

async def get_exchange_rates_api():
    """Получает курсы валют из внешнего API"""
    async with httpx.AsyncClient() as client:
        # Используем бесплатный API для примера
        response = await client.get("https://open.er-api.com/v6/latest/USD")
        data = response.json()

        if data["result"] == "success":
            rates = data["rates"]
            return {
                "date": datetime.now().date(),
                "usd_rub": rates.get("RUB", 90.0),
                "eur_rub": rates.get("RUB", 100.0) / rates.get("EUR", 0.9),
                "eur_usd": 1 / rates.get("EUR", 0.9),
                "updated_at": datetime.now()
            }
        return None


async def get_exchange_rates_history(days: int = 7):
    """Эмулирует получение исторических данных по курсам валют"""
    async with httpx.AsyncClient() as client:
        today = date.today()
        # Создаем список задач для параллельного выполнения
        tasks = []
        for i in range(days):
            # В реальном приложении здесь был бы запрос к API с датой
            # Для примера просто эмулируем задержку
            day = today - timedelta(days=i)
            tasks.append(asyncio.sleep(0.1))

        # Ждем завершения всех задач
        await asyncio.gather(*tasks)

        # Возвращаем фиктивные данные
        result = []
        for i in range(days):
            day = today - timedelta(days=i)
            result.append({
                "date": day,
                "usd_rub": 90.0 + i * 0.5,
                "eur_rub": 100.0 + i * 0.3,
                "eur_usd": (100.0 + i * 0.3) / (90.0 + i * 0.5),
                "updated_at": datetime.now() - timedelta(days=i)
            })
        return result


async def get_consolidated_financial_data():
    """Параллельно получает данные из разных источников"""
    async with httpx.AsyncClient() as client:
        # Запускаем все задачи параллельно
        exchange_rates_task = get_exchange_rates_api()
        # Эмулируем еще два запроса к разным API
        crypto_rates_task = client.get("https://api.coincap.io/v2/assets/bitcoin")
        stock_market_task = client.get("https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=MSFT&apikey=demo")

        # Ждем завершения всех задач
        exchange_rates, crypto_resp, stock_resp = await asyncio.gather(
            exchange_rates_task,
            crypto_rates_task,
            stock_market_task
        )

        # Обрабатываем результаты
        try:
            crypto_data = crypto_resp.json()
            crypto_price = crypto_data.get("data", {}).get("priceUsd", "N/A")
        except:
            crypto_price = "N/A"

        try:
            stock_data = stock_resp.json()
            stock_price = stock_data.get("Global Quote", {}).get("05. price", "N/A")
        except:
            stock_price = "N/A"

        # Возвращаем объединенные данные
        return {
            "exchange_rates": exchange_rates,
            "bitcoin_price_usd": crypto_price,
            "microsoft_stock_price": stock_price,
            "timestamp": datetime.now().isoformat()
        }

from typing import Optional
from loguru import logger


def get_news_sentiment(ticker: str, headlines: list[str]) -> Optional[float]:
    """
    Score a list of news headlines with FinBERT.
    Returns average sentiment in [-1, 1], or None if transformers is unavailable.
    positive=1, neutral=0, negative=-1
    """
    if not headlines:
        return None

    try:
        from transformers import pipeline
        pipe = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            return_all_scores=False,
            truncation=True,
        )
        label_map = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
        scores = []
        for h in headlines[:10]:
            result = pipe(h[:512])[0]
            scores.append(label_map.get(result["label"], 0.0))
        return round(sum(scores) / len(scores), 3) if scores else None
    except ImportError:
        logger.debug("transformers not installed — FinBERT unavailable. pip install transformers torch")
        return None
    except Exception as e:
        logger.warning(f"FinBERT sentiment failed for {ticker}: {e}")
        return None

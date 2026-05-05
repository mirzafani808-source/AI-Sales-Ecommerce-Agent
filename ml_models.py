# ml_models.py - Loads trained models from Colab files

import numpy as np
import joblib
import json
import os

# ============================================
# 1. FRAUD DETECTION (from fraud_model.pkl)
# ============================================

class FraudDetector:
    def __init__(self, model_path='fraud_model.pkl'):
        self.model = None
        if os.path.exists(model_path):
            try:
                self.model = joblib.load(model_path)
                print("✅ Fraud Detection Model loaded from Colab")
            except Exception as e:
                print(f"⚠️ Error loading fraud model: {e}")
                self.model = None
        else:
            print("⚠️ fraud_model.pkl not found")
    
    def predict(self, amount, items_count=1, suspicious_keywords=0, is_new_user=0, is_rush_hour=0):
        """Return fraud probability (0-100%)"""
        if self.model:
            try:
                # Model expects certain features - adjust based on training
                features = np.array([[amount, items_count, suspicious_keywords, is_new_user, is_rush_hour]])
                proba = self.model.predict_proba(features)[0]
                fraud_score = proba[1] * 100
                return round(fraud_score, 2)
            except:
                pass
        
        # Fallback logic (if model not loaded)
        score = 0
        if amount > 100000:
            score += 40
        if items_count > 5:
            score += 30
        if suspicious_keywords:
            score += 20
        if is_new_user:
            score += 10
        return min(score, 100)


# ============================================
# 2. RECOMMENDATION SYSTEM (from recommendations.json)
# ============================================

class RecommendationEngine:
    def __init__(self, rec_path='recommendations.json'):
        self.recommendations = {}
        if os.path.exists(rec_path):
            try:
                with open(rec_path, 'r') as f:
                    self.recommendations = json.load(f)
                print(f"✅ Recommendations loaded ({len(self.recommendations)} products)")
            except:
                print("⚠️ Error loading recommendations")
                self.recommendations = self.get_fallback_recs()
        else:
            print("⚠️ recommendations.json not found, using fallback")
            self.recommendations = self.get_fallback_recs()
    
    def get_fallback_recs(self):
        return {
            "laptop": ["mouse", "laptop bag", "keyboard"],
            "phone": ["phone case", "screen protector", "earphones"],
            "mouse": ["mouse pad", "laptop"],
            "keyboard": ["keyboard cover", "mouse"],
            "headphones": ["earphones", "phone case"],
            "shirt": ["jeans", "belt"],
            "shoes": ["socks", "shirt"]
        }
    
    def recommend(self, product_name):
        product_name = product_name.lower()
        for key, recs in self.recommendations.items():
            if key in product_name or product_name in key:
                return recs[:3]
        return ["similar items", "related products"]


# ============================================
# 3. SENTIMENT ANALYSIS (uses transformers)
# ============================================

class SentimentAnalyzer:
    def __init__(self, config_path='sentiment_config.json'):
        self.analyzer = None
        self._tried_loading = False
    
    def _ensure_loaded(self):
        """Lazy load the model only when needed"""
        if self._tried_loading:
            return
        self._tried_loading = True
        try:
            from transformers import pipeline
            self.analyzer = pipeline("sentiment-analysis", 
                                     model="distilbert-base-uncased-finetuned-sst-2-english")
            print("✅ Sentiment Analysis Model loaded")
        except Exception as e:
            print(f"⚠️ Sentiment model not loaded: {e}")
            self.analyzer = None
    
    def analyze(self, text):
        self._ensure_loaded()
        if self.analyzer:
            try:
                result = self.analyzer(text[:512])[0]
                return result['label']
            except:
                return "NEUTRAL"
        
        # Fallback: keyword based
        text_lower = text.lower()
        positive_words = ['good', 'great', 'amazing', 'love', 'best', 'awesome', 'excellent']
        negative_words = ['bad', 'worst', 'hate', 'terrible', 'poor', 'awful']
        
        if any(word in text_lower for word in positive_words):
            return "POSITIVE"
        if any(word in text_lower for word in negative_words):
            return "NEGATIVE"
        return "NEUTRAL"
    
    def get_emoji(self, text):
        sentiment = self.analyze(text)
        emojis = {"POSITIVE": "😊", "NEGATIVE": "😠", "NEUTRAL": "😐"}
        return emojis.get(sentiment, "😐")


# ============================================
# TEST (when run directly)
# ============================================

if __name__ == "__main__":
    print("\n=== Testing ML Models ===\n")
    
    fraud = FraudDetector()
    score = fraud.predict(150000, 5, 1, 1, 0)
    print(f"Fraud Score: {score}%")
    
    rec = RecommendationEngine()
    print(f"Recommendations for 'laptop': {rec.recommend('laptop')}")
    
    sentiment = SentimentAnalyzer()
    print(f"Sentiment: {sentiment.analyze('I love this product!')}")
    print(f"Emoji: {sentiment.get_emoji('This is terrible')}")
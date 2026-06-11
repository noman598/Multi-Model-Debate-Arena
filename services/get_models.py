from config.settings import Settings
settings = Settings()

def get_ollama_models_list():
    OLLAMA_MODELS = settings.OLLAMA_MODELS
    list_of_models = [model.strip() for model in OLLAMA_MODELS.split(',') if model.strip()]
    return list_of_models


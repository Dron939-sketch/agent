# load_to_vector_db.py
import json
import chromadb
from sentence_transformers import SentenceTransformer

# Загрузка БЗ
with open('varitype-kb-v2.json', 'r', encoding='utf-8') as f:
    kb = json.load(f)

# Инициализация
client = chromadb.Client()
collection = client.create_collection("varitype_knowledge")
model = SentenceTransformer('intfloat/multilingual-e5-large')

# Создание векторов для каждого уровня
documents = []
metadatas = []
ids = []

for vector, data in kb['vectors'].items():
    for level_key, level_data in data['levels'].items():
        # Текст для эмбеддинга
        text = f"""
        Масть: {vector} - {data['name']}
        Уровень: {level_data['name']}
        Суть: {data['essence']}
        Главный страх: {data['core_fear']}
        Главная потребность: {data['core_need']}
        Слепая зона: {data['blind_spot']}
        
        Поведение под давлением: {level_data['stress']}
        Отношение к ресурсам: {level_data['resources']}
        Понимание мира: {level_data['understanding']}
        Отношения: {level_data['relationships']}
        
        Что просит: {level_data['what_they_ask']}
        Что на самом деле нужно: {level_data['what_they_need']}
        Как вести: {level_data['how_to_lead']}
        
        Маршрут к лучшей жизни:
        {chr(10).join([f"{k}: {v}" for k, v in level_data['route_to_better_life'].items()])}
        """
        
        documents.append(text)
        metadatas.append({
            'vector': vector,
            'level': level_key,
            'varitype_level': level_data['varitype'],
            'name': level_data['name']
        })
        ids.append(f"{vector}_{level_key}")

# Создание эмбеддингов и загрузка
embeddings = model.encode(documents, normalize_embeddings=True).tolist()

collection.add(
    documents=documents,
    embeddings=embeddings,
    metadatas=metadatas,
    ids=ids
)

print(f"✅ Загружено {len(documents)} записей в векторную БД")

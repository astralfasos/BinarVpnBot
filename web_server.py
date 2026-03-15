from fastapi import FastAPI, HTTPException
import datetime
import base64
import os
import asyncpg

app = FastAPI()

# URL базы данных PostgreSQL (такой же, как у бота)
DATABASE_URL = os.environ.get("DATABASE_URL")

# Тот же шаблон подписки
SUBSCRIPTION_TEMPLATE = """#profile-title: base64:dC5tZS9CaW5hclZQTg==
#profile-update-interval: 24
#support-url: https://t.me/BinarVPN
trojan://lEjtI3pFYfU7O1UYozJcfZV5K6Fwfths@64.74.163.118:58536?security=tls&insecure=1&allowInsecure=1&type=tcp&headerType=none#🇨🇦 Canada, Pointe-Claire | [BL]
trojan://pawxrlkLcJ@145.223.70.200:44056/?type=grpc&serviceName=&authority=&security=reality&pbk=asrnd4KrFBe5Ygz7LkvvsdMG-YnvChftudLamEVisk8&fp=chrome&sni=www.icloud.com&sid=8a&spx=/#🇨🇦 Canada, Toronto | 🌐 | [BL]
trojan://q2GRUM1-odJBWq_KV6xv2fuNvu8ed-@195.66.25.251:443?security=tls&sni=8443.golden-cards.me&type=tcp#🇱🇹 Lithuania, Vilnius | [BL]
trojan://q2GRUM1-odJBWq_KV6xv2fuNvu8ed-@8443.golden-cards.me:443?security=tls&sni=8443.golden-cards.me#🇱🇹 Lithuania, Vilnius | [BL]
trojan://q2GRUM1-odJBWq_KV6xv2fuNvu8ed-@8443.golden-cards.me:443?security=tls&sni=8443.golden-cards.me&fp=qq&insecure=0&allowInsecure=0&type=tcp&headerType=none#🇱🇹 Lithuania, Vilnius | [BL]
trojan://q2GRUM1-odJBWq_KV6xv2fuNvu8ed-@8443.golden-cards.me:443?type=raw&headerType=none&security=tls#🇱🇹 Lithuania, Vilnius | [BL]
trojan://wp9IsiY82uQhcmgNC1eoBM@80.173.231.254:12420?security=tls&sni=%F0%9F%94%92%20%5BBy%20EbraSha%5D%20&insecure=1&allowInsecure=1&type=tcp&headerType=none#🇳🇴 Norway, Oslo (Alna District) | [BL]
trojan://wp9IsiY82uQhcmgNC1eoBM@80.173.231.254:12420?security=tls&sni=%F0%9F%94%92%20By%20EbraSha%20&insecure=1&allowInsecure=1&type=tcp&headerType=none#🇳🇴 Norway, Oslo (Alna District) | [BL]
trojan://zp630tdUuD@194.150.166.151:52047/?type=grpc&serviceName=&authority=&security=reality&pbk=4o28aGSIz_r6Fa9sG7ZjgeT764t3bVJKmC9RDwIff38&fp=chrome&sni=aws.amazon.com&sid=1abe0c286879&spx=%2F#🇬🇧 United Kingdom, London | [BL]
trojan://kkzh2prsyr2ik47as615@64.94.95.118:57142?type=tcp&security=tls&sni=64.94.95.118&fp=random&allowInsecure=1#🇺🇸 United States, Dallas | [BL]"""

async def get_user(user_id: int):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
    await conn.close()
    return row

async def is_subscription_active(user_id: int) -> bool:
    row = await get_user(user_id)
    if not row:
        return False
    until = row['subscription_until']
    if not until:
        return False
    if isinstance(until, datetime.datetime):
        expire = until
    else:
        expire = datetime.datetime.fromisoformat(str(until))
    return expire > datetime.datetime.now()

async def generate_subscription_file(user_id: int) -> str:
    row = await get_user(user_id)
    expire_date = row['subscription_until']
    if isinstance(expire_date, str):
        expire_date = datetime.datetime.fromisoformat(expire_date)
    expire_timestamp = int(expire_date.timestamp())
    userinfo_line = f"#subscription-userinfo: upload=0; download=0; total=0; expire={expire_timestamp}"
    full_text = userinfo_line + "\n" + SUBSCRIPTION_TEMPLATE
    return base64.b64encode(full_text.encode()).decode()

@app.get("/sub/{user_id}")
async def get_subscription(user_id: int):
    if not await is_subscription_active(user_id):
        raise HTTPException(status_code=404, detail="Subscription not found or expired")
    return await generate_subscription_file(user_id)
import os
import requests
from openai import OpenAI
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime

BOSTON_LAT = 42.3601
BOSTON_LON = -71.0589

WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Moderate rain showers",
    82: "Heavy rain showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


def get_boston_weather():
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": BOSTON_LAT,
            "longitude": BOSTON_LON,
            "current": [
                "temperature_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
                "relative_humidity_2m",
            ],
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "forecast_days": 1,
        },
        timeout=10,
    )
    resp.raise_for_status()
    c = resp.json()["current"]
    return {
        "temperature": c["temperature_2m"],
        "feels_like": c["apparent_temperature"],
        "precipitation": c["precipitation"],
        "description": WMO_CODES.get(c["weather_code"], f"Code {c['weather_code']}"),
        "wind_speed": c["wind_speed_10m"],
        "humidity": c["relative_humidity_2m"],
    }


def generate_outfit(weather):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    weather_text = (
        f"Temperature: {weather['temperature']}°F (feels like {weather['feels_like']}°F)\n"
        f"Conditions: {weather['description']}\n"
        f"Wind: {weather['wind_speed']} mph\n"
        f"Humidity: {weather['humidity']}%\n"
        f"Precipitation: {weather['precipitation']} mm"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f"""You are a personal stylist. Based on today's Boston weather, suggest a complete, stylish outfit.

{weather_text}

Respond in exactly this format with no extra text:
DESCRIPTION: [2-3 sentences describing what to wear and why it suits the weather]
IMAGE_PROMPT: [A detailed DALL-E prompt: full-body shot of a stylish person wearing the outfit, standing on a Boston street. Describe every clothing item, colors, fabrics, and accessories. Photorealistic, fashion photography style, natural lighting.]""",
            }
        ],
    )

    text = response.choices[0].message.content
    description = ""
    image_prompt = ""

    if "DESCRIPTION:" in text and "IMAGE_PROMPT:" in text:
        parts = text.split("IMAGE_PROMPT:")
        description = parts[0].replace("DESCRIPTION:", "").strip()
        image_prompt = parts[1].strip()
    else:
        description = text.strip()
        image_prompt = (
            f"A stylish person wearing weather-appropriate clothing for {weather['temperature']}°F "
            f"{weather['description'].lower()} weather, standing on a Boston city street. "
            "Full body shot, photorealistic, fashion photography."
        )

    return description, image_prompt


def generate_image(prompt):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    result = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    image_url = result.data[0].url
    resp = requests.get(image_url, timeout=30)
    resp.raise_for_status()
    return resp.content


def send_email(image_bytes, outfit_description, weather):
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    email_from = os.environ["EMAIL_FROM"]
    email_password = os.environ["EMAIL_PASSWORD"].strip()

    # ✅ This will work in GitHub Actions since file is in repo
    emails_file = os.path.join(os.path.dirname(__file__), "emails.txt")
    with open(emails_file) as f:
        recipients = [
            line.strip() for line in f if line.strip() and not line.startswith("#")
        ]

    today = datetime.now().strftime("%A, %B %d, %Y")

    msg = MIMEMultipart("related")
    msg["Subject"] = f"Your Outfit for Today — {today}"
    msg["From"] = email_from
    msg["To"] = ", ".join(recipients)

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333;">
      <h2>Good morning! ☀️</h2>
      <p>Here's what to wear today in Boston</p>

      <div>
        <strong>Weather:</strong><br>
        {weather["temperature"]}°F (feels like {weather["feels_like"]}°F)<br>
        {weather["description"]}<br>
        Wind {weather["wind_speed"]} mph · Humidity {weather["humidity"]}%
      </div>

      <p>{outfit_description}</p>
      <img src="cid:outfit" style="width: 100%; border-radius: 12px;" />
    </body>
    </html>
    """

    alternative = MIMEMultipart("alternative")
    msg.attach(alternative)
    alternative.attach(MIMEText(html, "html"))

    img_part = MIMEImage(image_bytes)
    img_part.add_header("Content-ID", "<outfit>")
    msg.attach(img_part)

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(email_from, email_password)
        server.sendmail(email_from, recipients, msg.as_string())

    print(f"✓ Email sent to {', '.join(recipients)}")


def main():
    print("→ Fetching weather...")
    weather = get_boston_weather()

    print("→ Generating outfit...")
    description, image_prompt = generate_outfit(weather)

    print("→ Generating image...")
    image_bytes = generate_image(image_prompt)

    print("→ Sending email...")
    send_email(image_bytes, description, weather)

    print("Done!")


if __name__ == "__main__":
    main()

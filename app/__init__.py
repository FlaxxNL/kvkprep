import csv
import hmac
import io
import json
import logging
import mimetypes
import os
import secrets
import sqlite3
import time
from logging.handlers import RotatingFileHandler
from flask_babel import Babel

import markdown
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename

from config import Config

from . import database, logic
from .logic import (
    format_minutes,
    generate_short_uid,
    get_ordered_active_days,
    get_superadmin_metrics,
    validate_custom_slug,
)

# Ensure .js files are served with the correct MIME type
mimetypes.add_type("application/javascript", ".js")


def validate_safe_url(url: str | None) -> str | None:
    """Ensure URL uses only safe HTTP(S) or static relative schemes."""
    if not url or not isinstance(url, str):
        return None
    cleaned = url.strip()
    if cleaned.startswith(("http://", "https://", "/static/")):
        return cleaned
    return None


def generate_slot_labels(slot_count=49):
    labels = []
    for i in range(slot_count):
        if slot_count == 48:
            start_total_minutes = i * 30
        else:
            start_total_minutes = (i * 30) - 15

        if start_total_minutes < 0:
            start_total_minutes += 24 * 60

        start_hour = start_total_minutes // 60
        start_min = start_total_minutes % 60

        end_total_minutes = start_total_minutes + 30
        end_hour = (end_total_minutes // 60) % 24
        end_min = end_total_minutes % 60

        labels.append(
            f"{start_hour:02d}:{start_min:02d}-\u200b{end_hour:02d}:{end_min:02d}"
        )
    return labels


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    babel = Babel(app)
    CSRFProtect(app)
    database.init_app(app)

    SUPPORTED_LANGUAGES = {
        "en": "English",
        "tr": "Türkçe",
        "ru": "Русский",
        "uk": "Українська",
        "es": "Español",
        "fr": "Français",
        "de": "Deutsch",
        "pl": "Polski",
        "it": "Italiano",
        "pt": "Português",
        "nl": "Nederlands",
    }

    TRANSLATIONS = {
        "en": {
            "title": "Kingshot KvK Prep",
            "tagline": "Prepare your kingdom. Dominate KvK.",
            "welcome": "Welcome",
            "intro1": "This tool helps Kingshot players and alliance leadership prepare for Kingdom vs Kingdom.",
            "intro2": "Players can submit their available resources and speedups, allowing leadership to better coordinate and prepare for KvK.",
            "how_it_works": "How does it work?",
            "step1_title": "Your leadership creates an event",
            "step1_text": "Your alliance leadership creates a KvK event and shares the link with the players.",
            "step2_title": "Players submit their information",
            "step2_text": "Enter your player information, resources and available speedups.",
            "step3_title": "Leadership coordinates KvK",
            "step3_text": "Leadership can use the collected information to coordinate the alliance during KvK.",
            "guide": "Read the full User Guide & Tutorial →",
            "language": "Language",
            "more_languages": "More languages coming soon.",
            "github": "GitHub",
        },

        "tr": {
            "title": "Kingshot KvK Hazırlığı",
            "tagline": "Krallığını hazırla. KvK'ya hükmet.",
            "welcome": "Hoş Geldiniz",
            "intro1": "Bu araç, Kingshot oyuncularının ve ittifak liderlerinin Krallıklar Arası Savaş'a hazırlanmasına yardımcı olur.",
            "intro2": "Oyuncular sahip oldukları kaynakları ve hızlandırmaları göndererek liderliğin KvK için daha iyi koordinasyon ve hazırlık yapmasını sağlar.",
            "how_it_works": "Nasıl çalışır?",
            "step1_title": "Liderliğiniz bir etkinlik oluşturur",
            "step1_text": "İttifak liderliğiniz bir KvK etkinliği oluşturur ve bağlantıyı oyuncularla paylaşır.",
            "step2_title": "Oyuncular bilgilerini gönderir",
            "step2_text": "Oyuncu bilgilerinizi, kaynaklarınızı ve mevcut hızlandırmalarınızı girin.",
            "step3_title": "Liderlik KvK'yı koordine eder",
            "step3_text": "Liderlik, toplanan bilgileri kullanarak KvK sırasında ittifakı koordine edebilir.",
            "guide": "Kullanım Kılavuzu ve Eğitimin tamamını okuyun →",
            "language": "Dil",
            "more_languages": "Daha fazla dil yakında eklenecek.",
            "github": "GitHub",
        },

        "ru": {
            "title": "Подготовка к KvK в Kingshot",
            "tagline": "Подготовьте своё королевство. Победите в KvK.",
            "welcome": "Добро пожаловать",
            "intro1": "Этот инструмент помогает игрокам Kingshot и руководству альянса подготовиться к войне королевств.",
            "intro2": "Игроки могут указать доступные ресурсы и ускорения, чтобы руководство могло лучше координировать подготовку к KvK.",
            "how_it_works": "Как это работает?",
            "step1_title": "Руководство создаёт событие",
            "step1_text": "Руководство вашего альянса создаёт событие KvK и отправляет ссылку игрокам.",
            "step2_title": "Игроки отправляют информацию",
            "step2_text": "Укажите информацию об игроке, ресурсы и доступные ускорения.",
            "step3_title": "Руководство координирует KvK",
            "step3_text": "Руководство использует собранную информацию для координации альянса во время KvK.",
            "guide": "Открыть полное руководство и инструкцию →",
            "language": "Язык",
            "more_languages": "Скоро появятся новые языки.",
            "github": "GitHub",
        },

        "nl": {
            "title": "Kingshot KvK Voorbereiding",
            "tagline": "Bereid je koninkrijk voor. Beheers KvK.",
            "welcome": "Welkom",
            "intro1": "Deze tool helpt Kingshot-spelers en alliantie-leiders zich voor te bereiden op Kingdom vs Kingdom.",
            "intro2": "Spelers kunnen hun beschikbare grondstoffen en speedups doorgeven, zodat de leiding de KvK beter kan coördineren en voorbereiden.",
            "how_it_works": "Hoe werkt het?",
            "step1_title": "Jullie leiding maakt een event aan",
            "step1_text": "De leiding van je alliantie maakt een KvK-event aan en deelt de link met de spelers.",
            "step2_title": "Spelers geven hun informatie door",
            "step2_text": "Vul je spelersinformatie, grondstoffen en beschikbare speedups in.",
            "step3_title": "De leiding coördineert KvK",
            "step3_text": "De leiding kan de verzamelde informatie gebruiken om de alliantie tijdens KvK te coördineren.",
            "guide": "Bekijk de volledige gebruikershandleiding en tutorial →",
            "language": "Taal",
            "more_languages": "Meer talen volgen binnenkort.",
            "github": "GitHub",
        },

        "de": {
            "title": "Kingshot KvK Vorbereitung",
            "tagline": "Bereitet euer Königreich vor. Bezwingt KvK.",
            "welcome": "Willkommen",
            "intro1": "Dieses Tool hilft Kingshot-Spielern und der Allianzleitung bei der Vorbereitung auf Kingdom vs Kingdom.",
            "intro2": "Spieler können ihre verfügbaren Ressourcen und Beschleuniger angeben, damit die Leitung KvK besser koordinieren und vorbereiten kann.",
            "how_it_works": "Wie funktioniert es?",
            "step1_title": "Eure Leitung erstellt ein Event",
            "step1_text": "Die Allianzleitung erstellt ein KvK-Event und teilt den Link mit den Spielern.",
            "step2_title": "Spieler übermitteln ihre Informationen",
            "step2_text": "Gebt eure Spielerinformationen, Ressourcen und verfügbaren Beschleuniger ein.",
            "step3_title": "Die Leitung koordiniert KvK",
            "step3_text": "Die Leitung kann die gesammelten Informationen nutzen, um die Allianz während KvK zu koordinieren.",
            "guide": "Vollständige Anleitung und Tutorial lesen →",
            "language": "Sprache",
            "more_languages": "Weitere Sprachen folgen bald.",
            "github": "GitHub",
        },

        "fr": {
            "title": "Préparation KvK Kingshot",
            "tagline": "Préparez votre royaume. Dominez le KvK.",
            "welcome": "Bienvenue",
            "intro1": "Cet outil aide les joueurs de Kingshot et les dirigeants d'alliance à se préparer pour Kingdom vs Kingdom.",
            "intro2": "Les joueurs peuvent indiquer leurs ressources et accélérations disponibles afin que les dirigeants puissent mieux coordonner la préparation au KvK.",
            "how_it_works": "Comment ça marche ?",
            "step1_title": "Votre direction crée un événement",
            "step1_text": "La direction de votre alliance crée un événement KvK et partage le lien avec les joueurs.",
            "step2_title": "Les joueurs envoient leurs informations",
            "step2_text": "Saisissez vos informations de joueur, vos ressources et vos accélérations disponibles.",
            "step3_title": "La direction coordonne le KvK",
            "step3_text": "La direction peut utiliser les informations recueillies pour coordonner l'alliance pendant le KvK.",
            "guide": "Lire le guide et tutoriel complet →",
            "language": "Langue",
            "more_languages": "D'autres langues seront bientôt disponibles.",
            "github": "GitHub",
        },

        "es": {
            "title": "Preparación KvK de Kingshot",
            "tagline": "Prepara tu reino. Domina el KvK.",
            "welcome": "Bienvenido",
            "intro1": "Esta herramienta ayuda a los jugadores de Kingshot y a los líderes de alianza a prepararse para Kingdom vs Kingdom.",
            "intro2": "Los jugadores pueden indicar sus recursos y aceleradores disponibles para que los líderes puedan coordinar mejor la preparación del KvK.",
            "how_it_works": "¿Cómo funciona?",
            "step1_title": "El liderazgo crea un evento",
            "step1_text": "El liderazgo de tu alianza crea un evento de KvK y comparte el enlace con los jugadores.",
            "step2_title": "Los jugadores envían su información",
            "step2_text": "Introduce tu información de jugador, recursos y aceleradores disponibles.",
            "step3_title": "El liderazgo coordina el KvK",
            "step3_text": "El liderazgo puede utilizar la información recopilada para coordinar la alianza durante el KvK.",
            "guide": "Leer la guía y tutorial completos →",
            "language": "Idioma",
            "more_languages": "Próximamente habrá más idiomas.",
            "github": "GitHub",
        },

        "pl": {
            "title": "Przygotowanie KvK Kingshot",
            "tagline": "Przygotuj swoje królestwo. Zdominuj KvK.",
            "welcome": "Witamy",
            "intro1": "To narzędzie pomaga graczom Kingshot i liderom sojuszu przygotować się do Kingdom vs Kingdom.",
            "intro2": "Gracze mogą podać dostępne zasoby i przyspieszenia, aby liderzy mogli lepiej koordynować przygotowania do KvK.",
            "how_it_works": "Jak to działa?",
            "step1_title": "Liderzy tworzą wydarzenie",
            "step1_text": "Liderzy twojego sojuszu tworzą wydarzenie KvK i udostępniają link graczom.",
            "step2_title": "Gracze przesyłają informacje",
            "step2_text": "Podaj informacje o graczu, zasoby i dostępne przyspieszenia.",
            "step3_title": "Liderzy koordynują KvK",
            "step3_text": "Liderzy mogą wykorzystać zebrane informacje do koordynowania sojuszu podczas KvK.",
            "guide": "Przeczytaj pełny przewodnik i samouczek →",
            "language": "Język",
            "more_languages": "Wkrótce pojawią się kolejne języki.",
            "github": "GitHub",
        },

        "it": {
            "title": "Preparazione KvK di Kingshot",
            "tagline": "Prepara il tuo regno. Domina il KvK.",
            "welcome": "Benvenuto",
            "intro1": "Questo strumento aiuta i giocatori di Kingshot e i leader dell'alleanza a prepararsi per Kingdom vs Kingdom.",
            "intro2": "I giocatori possono indicare le risorse e gli acceleratori disponibili, permettendo ai leader di coordinare meglio la preparazione al KvK.",
            "how_it_works": "Come funziona?",
            "step1_title": "La leadership crea un evento",
            "step1_text": "La leadership della tua alleanza crea un evento KvK e condivide il link con i giocatori.",
            "step2_title": "I giocatori inviano le informazioni",
            "step2_text": "Inserisci le informazioni del giocatore, le risorse e gli acceleratori disponibili.",
            "step3_title": "La leadership coordina il KvK",
            "step3_text": "La leadership può utilizzare le informazioni raccolte per coordinare l'alleanza durante il KvK.",
            "guide": "Leggi la guida e il tutorial completi →",
            "language": "Lingua",
            "more_languages": "Presto saranno disponibili altre lingue.",
            "github": "GitHub",
        },

        "pt": {
            "title": "Preparação KvK do Kingshot",
            "tagline": "Prepare seu reino. Domine o KvK.",
            "welcome": "Bem-vindo",
            "intro1": "Esta ferramenta ajuda os jogadores de Kingshot e os líderes da aliança a se prepararem para Kingdom vs Kingdom.",
            "intro2": "Os jogadores podem informar seus recursos e aceleradores disponíveis, permitindo que a liderança coordene melhor a preparação para o KvK.",
            "how_it_works": "Como funciona?",
            "step1_title": "A liderança cria um evento",
            "step1_text": "A liderança da sua aliança cria um evento KvK e compartilha o link com os jogadores.",
            "step2_title": "Os jogadores enviam suas informações",
            "step2_text": "Informe seus dados de jogador, recursos e aceleradores disponíveis.",
            "step3_title": "A liderança coordena o KvK",
            "step3_text": "A liderança pode usar as informações coletadas para coordenar a aliança durante o KvK.",
            "guide": "Leia o guia e tutorial completo →",
            "language": "Idioma",
            "more_languages": "Mais idiomas em breve.",
            "github": "GitHub",
        },

        "uk": {
            "title": "Підготовка до KvK у Kingshot",
            "tagline": "Підготуйте своє королівство. Перемагайте в KvK.",
            "welcome": "Ласкаво просимо",
            "intro1": "Цей інструмент допомагає гравцям Kingshot та керівництву альянсу підготуватися до війни королівств.",
            "intro2": "Гравці можуть вказати доступні ресурси та прискорення, щоб керівництво могло краще координувати підготовку до KvK.",
            "how_it_works": "Як це працює?",
            "step1_title": "Керівництво створює подію",
            "step1_text": "Керівництво вашого альянсу створює подію KvK і ділиться посиланням з гравцями.",
            "step2_title": "Гравці надсилають інформацію",
            "step2_text": "Введіть інформацію про гравця, ресурси та доступні прискорення.",
            "step3_title": "Керівництво координує KvK",
            "step3_text": "Керівництво може використовувати зібрану інформацію для координації альянсу під час KvK.",
            "guide": "Відкрити повний посібник та інструкцію →",
            "language": "Мова",
            "more_languages": "Незабаром з'являться нові мови.",
            "github": "GitHub",
        },
    }

    def get_locale():
        return session.get("language", "en")

    def translate(key):
        language = get_locale()
        return TRANSLATIONS.get(language, TRANSLATIONS["en"]).get(
            key, TRANSLATIONS["en"].get(key, key)
        )

    @app.route("/language/<language>")
    def set_language(language):
        if language in SUPPORTED_LANGUAGES:
            session["language"] = language

        return redirect(request.referrer or url_for("index"))

    @app.context_processor
    def inject_language_data():
        return {
            "supported_languages": SUPPORTED_LANGUAGES,
            "current_language": get_locale(),
            "t": translate,
        }

    def get_locale():
        return session.get("language", "en")

    @app.context_processor
    def inject_language_data():
        return {
            "supported_languages": SUPPORTED_LANGUAGES,
            "current_language": get_locale(),
        }
    
    # Setup Audit Logging
    log_dir = os.path.join(app.root_path, "..", "logs")
    os.makedirs(log_dir, exist_ok=True)

    audit_handler = RotatingFileHandler(
        os.path.join(log_dir, "audit.log"), maxBytes=1000000, backupCount=5
    )
    audit_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    audit_logger = logging.getLogger("audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.addHandler(audit_handler)
    app.audit_logger = audit_logger

    # Make the label generator available to all templates
    @app.context_processor
    def inject_global_config():
        slot_count = 49
        try:
            event_uid = (
                request.view_args.get("event_uid") if request.view_args else None
            )
            if event_uid:
                db = database.get_db()
                row = db.execute(
                    "SELECT slot_count FROM events WHERE uid = ?", (event_uid,)
                ).fetchone()
                if row and row[0] is not None:
                    slot_count = row[0]
        except (RuntimeError, Exception):  # noqa: BLE001, S110
            pass

        return {
            "slot_labels": generate_slot_labels(slot_count),
            "enable_screenshot_upload": Config.ENABLE_SCREENSHOT_UPLOAD,
            "ga_measurement_id": Config.GA_MEASUREMENT_ID,
        }

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://www.google-analytics.com;"
        )
        response.headers["Content-Security-Policy"] = csp
        return response

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/guide")
    def guide():
        try:
            with open("README.md", "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Filter out technical badges for the in-app guide
            filtered_lines = [
                line for line in lines if not line.strip().startswith("[![")
            ]
            content = "".join(filtered_lines)

            # Replace local file paths with web-accessible static paths for the in-app guide
            content = content.replace("app/static/images/", "/static/images/")
            html_content = markdown.markdown(
                content, extensions=["extra", "toc", "fenced_code"]
            )
            return render_template("guide.html", content=html_content)
        except FileNotFoundError:
            return "Guide not found", 404

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(
            os.path.join(app.root_path, "static"),
            "favicon.svg",
            mimetype="image/svg+xml",
        )

    @app.route("/create", methods=["POST"])
    def create_event():
        event_name = request.form.get("event_name", "").strip()
        if not event_name:
            event_name = "Untitled Event"

        research_day = request.form.get("research_day", "5")
        try:
            slot_count = int(request.form.get("slot_count", "49"))
            if slot_count not in [48, 49]:
                slot_count = 49
        except ValueError:
            slot_count = 49

        db = database.get_db()

        # Handle custom slug or auto-generated short UID
        custom_slug = request.form.get("custom_slug", "").strip()
        if custom_slug:
            is_valid, err_msg = validate_custom_slug(custom_slug, db)
            if not is_valid:
                return err_msg, 400
            uid = custom_slug
        else:
            # Generate unique short UID with collision check
            while True:
                candidate_uid = generate_short_uid(8)
                exists = db.execute(
                    "SELECT 1 FROM events WHERE uid = ?", (candidate_uid,)
                ).fetchone()
                if not exists:
                    uid = candidate_uid
                    break

        admin_secret = secrets.token_urlsafe(16)

        active_days = {
            "construction": True,
            "training": True,
            "research": True,
            "research_day": int(research_day),
        }

        raw_server_id = request.form.get("server_id", "").strip()
        server_id = None
        if raw_server_id:
            try:
                parsed_id = int(raw_server_id)
                if parsed_id > 0:
                    server_id = parsed_id
            except ValueError:
                server_id = None

        db.execute(
            "INSERT INTO events (uid, name, active_days, admin_secret, slot_count, server_id) VALUES (?, ?, ?, ?, ?, ?)",
            (
                uid,
                event_name,
                json.dumps(active_days),
                admin_secret,
                slot_count,
                server_id,
            ),
        )
        db.commit()

        return redirect(url_for("success", event_uid=uid, secret=admin_secret))

    @app.route("/success/<event_uid>")
    def success(event_uid):
        secret = request.args.get("secret")

        player_url = url_for("player_form", event_uid=event_uid, _external=True)
        admin_url = url_for(
            "admin_dashboard", event_uid=event_uid, secret=secret, _external=True
        )
        finalized_url = url_for(
            "locked_appointments", event_uid=event_uid, _external=True
        )

        return render_template(
            "success.html",
            player_url=player_url,
            admin_url=admin_url,
            finalized_url=finalized_url,
        )

    @app.route("/event/<event_uid>/finalized")
    def locked_appointments(event_uid):
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()

        if event is None:
            return "Event not found", 404

        active_days_config = json.loads(event["active_days"])
        active_days = get_ordered_active_days(active_days_config)

        # Create a dictionary from the database row for the template
        event_dict = {
            "uid": event["uid"],
            "name": event["name"],
            "active_days": active_days_config,
            "server_id": event["server_id"],
        }

        # Fetch all assignments
        assignments_raw = db.execute(
            "SELECT * FROM assignments WHERE event_uid = ?",
            (event_uid,),
        ).fetchall()

        # Fetch submissions to get player/alliance names
        submissions_raw = db.execute(
            "SELECT * FROM submissions WHERE event_uid = ?", (event_uid,)
        ).fetchall()
        submissions_map = {
            (sub["day_type"], sub["player_id"]): sub for sub in submissions_raw
        }

        # Group rich assignments by day_type
        all_assignments = {day: {} for day in active_days}
        for a in assignments_raw:
            day_type = a["day_type"]
            player_id = a["player_id"]
            if day_type in all_assignments:
                submission = submissions_map.get((day_type, player_id))
                if submission:
                    all_assignments[day_type][a["slot_index"]] = {
                        "player_id": player_id,
                        "player_name": submission["player_name"],
                        "alliance_name": submission["alliance_name"],
                        "avatar_url": submission["avatar_url"],
                        "is_locked": bool(a["is_locked"]),
                    }

        return render_template(
            "locked_appointments.html",
            event=event_dict,
            active_days=active_days,
            assignments=all_assignments,
        )

    @app.route("/event/<event_uid>")
    def player_form(event_uid):
        db = database.get_db()
        # Use a dictionary cursor for easier row access
        db.row_factory = sqlite3.Row
        event_cursor = db.execute("SELECT * FROM events WHERE uid = ?", (event_uid,))
        event = event_cursor.fetchone()

        if event is None:
            return "Event not found", 404

        active_days_config = json.loads(event["active_days"])
        active_days = get_ordered_active_days(active_days_config)
        # Create a dictionary from the database row
        event_dict = {
            "uid": event["uid"],
            "name": event["name"],
            "active_days": active_days_config,
            "server_id": event["server_id"],
        }

        return render_template(
            "player_form.html", event=event_dict, active_days=active_days
        )

    @app.route("/event/<event_uid>/submit", methods=["POST"])
    def submit(event_uid):
        db = database.get_db()
        player_id = request.form.get("player_id", "").strip()
        player_name = request.form.get("player_name", "").strip()
        alliance_name = request.form.get("alliance_name", "").strip()

        # Server-side validation
        if not player_id.isdigit():
            return "Invalid Player ID: Must be numeric", 400

        if not player_name:
            return "Invalid Player Name: Cannot be empty", 400

        app.audit_logger.info(
            f"SUBMISSION: Player {player_name} ({player_id}) submitted resources for event {event_uid}"
        )

        # Handle backpack screenshot upload
        backpack_url = None
        if Config.ENABLE_SCREENSHOT_UPLOAD and "backpack_screenshot" in request.files:
            file = request.files["backpack_screenshot"]
            if file and file.filename:
                # Validate file extension
                allowed_extensions = {"png", "jpg", "jpeg", "gif"}
                extension = file.filename.rsplit(".", 1)[-1].lower()
                if extension not in allowed_extensions:
                    return "Invalid file type. Only images are allowed.", 400

                # Validate image header / magic bytes
                header = file.read(16)
                file.seek(0)
                is_png = header.startswith(b"\x89PNG\r\n\x1a\n")
                is_jpeg = header.startswith(b"\xff\xd8\xff")
                is_gif = header.startswith((b"GIF87a", b"GIF89a"))
                if not (is_png or is_jpeg or is_gif):
                    return (
                        "Invalid image content. Only PNG, JPEG, and GIF images are allowed.",
                        400,
                    )

                # Create upload directory if it doesn't exist
                upload_dir = os.path.join(app.static_folder, "uploads")
                os.makedirs(upload_dir, exist_ok=True)

                # Generate unique filename: event_uid + player_id + timestamp + original filename
                filename = secure_filename(
                    f"{event_uid}_{player_id}_{int(time.time())}_{file.filename}"
                )
                file.save(os.path.join(upload_dir, filename))
                backpack_url = validate_safe_url(
                    url_for("static", filename=f"uploads/{filename}")
                )

        # First, delete all previous submissions and assignments for this player and event.
        db.execute(
            "DELETE FROM submissions WHERE event_uid = ? AND player_id = ?",
            (event_uid, player_id),
        )
        db.execute(
            "DELETE FROM assignments WHERE event_uid = ? AND player_id = ?",
            (event_uid, player_id),
        )

        # Then, insert the new submissions from the form.
        avatar_url = validate_safe_url(request.form.get("avatar_url"))

        # --- Process Construction Submission ---
        construction_speedups = int(request.form.get("speedups-construction") or 0)
        truegold = int(request.form.get("truegold") or 0)
        tempered_truegold = int(request.form.get("tempered_truegold") or 0)
        feasible_slots = request.form.get("slots-construction", "[]")
        if (
            construction_speedups > 0 or truegold > 0 or tempered_truegold > 0
        ) and feasible_slots != "[]":
            day_type = "construction"
            score = (
                (construction_speedups * 30)
                + (truegold * 2000)
                + (tempered_truegold * 30000)
            )
            raw_data = {
                "speedups": construction_speedups,
                "truegold": truegold,
                "tempered_truegold": tempered_truegold,
            }
            submission_id = f"{event_uid}_{player_id}_{day_type}"
            db.execute(
                "INSERT INTO submissions (id, event_uid, day_type, player_name, player_id, avatar_url, backpack_url, alliance_name, resources, raw_data, feasible_slots) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    submission_id,
                    event_uid,
                    day_type,
                    player_name,
                    player_id,
                    avatar_url,
                    backpack_url,
                    alliance_name,
                    score,
                    json.dumps(raw_data),
                    feasible_slots,
                ),
            )

        # --- Process Training Submission ---
        training_speedups = int(request.form.get("speedups-training") or 0)
        feasible_slots = request.form.get("slots-training", "[]")
        if training_speedups > 0 and feasible_slots != "[]":
            day_type = "training"
            score = training_speedups * 90
            raw_data = {"speedups": training_speedups}
            submission_id = f"{event_uid}_{player_id}_{day_type}"
            db.execute(
                "INSERT INTO submissions (id, event_uid, day_type, player_name, player_id, avatar_url, backpack_url, alliance_name, resources, raw_data, feasible_slots) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    submission_id,
                    event_uid,
                    day_type,
                    player_name,
                    player_id,
                    avatar_url,
                    backpack_url,
                    alliance_name,
                    score,
                    json.dumps(raw_data),
                    feasible_slots,
                ),
            )

        # --- Process Research Submission ---
        research_speedups = int(request.form.get("speedups-research") or 0)
        truegold_dust = int(request.form.get("truegold_dust") or 0)
        feasible_slots = request.form.get("slots-research", "[]")
        if (research_speedups > 0 or truegold_dust > 0) and feasible_slots != "[]":
            day_type = "research"
            score = (research_speedups * 30) + (truegold_dust * 1000)
            raw_data = {"speedups": research_speedups, "truegold_dust": truegold_dust}
            submission_id = f"{event_uid}_{player_id}_{day_type}"
            db.execute(
                "INSERT INTO submissions (id, event_uid, day_type, player_name, player_id, avatar_url, backpack_url, alliance_name, resources, raw_data, feasible_slots) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    submission_id,
                    event_uid,
                    day_type,
                    player_name,
                    player_id,
                    avatar_url,
                    backpack_url,
                    alliance_name,
                    score,
                    json.dumps(raw_data),
                    feasible_slots,
                ),
            )

        db.commit()

        return redirect(url_for("submission_success"))

    @app.route("/submission-success")
    def submission_success():
        return render_template("submission_success.html")

    @app.route("/admin/<event_uid>")
    def admin_dashboard(event_uid):
        db = database.get_db()
        db.row_factory = sqlite3.Row

        secret = request.args.get("secret")
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()

        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        active_days_config = json.loads(event["active_days"])
        active_days = get_ordered_active_days(active_days_config)

        # Create a dictionary from the database row for the template
        event_dict = {
            "uid": event["uid"],
            "name": event["name"],
            "active_days": active_days_config,
            "server_id": event["server_id"],
        }

        # 1. Group submissions by day_type
        submissions_raw = db.execute(
            "SELECT * FROM submissions WHERE event_uid = ? ORDER BY resources DESC",
            (event_uid,),
        ).fetchall()
        submissions_by_day = {day: [] for day in active_days}
        for row in submissions_raw:
            if row["day_type"] in submissions_by_day:
                # Convert sqlite3.Row to a dictionary to allow item assignment
                sub_dict = dict(row)
                try:
                    sub_dict["raw_resources"] = json.loads(row["raw_data"])
                except (json.JSONDecodeError, TypeError):
                    sub_dict["raw_resources"] = {}
                submissions_by_day[row["day_type"]].append(sub_dict)

        # 2. Group assignments and related data by day_type
        assignments_raw = db.execute(
            "SELECT * FROM assignments WHERE event_uid = ?", (event_uid,)
        ).fetchall()
        rich_assignments = {day: {} for day in active_days}
        assignments_by_sub_id = {}
        submissions_map = {
            (sub["day_type"], sub["player_id"]): sub for sub in submissions_raw
        }

        for a in assignments_raw:
            day_type = a["day_type"]
            player_id = a["player_id"]
            if day_type in rich_assignments:
                submission = submissions_map.get((day_type, player_id))
                if submission:
                    rich_assignments[day_type][a["slot_index"]] = {
                        "player_id": player_id,
                        "player_name": submission["player_name"],
                        "alliance_name": submission["alliance_name"],
                        "avatar_url": submission["avatar_url"],
                        "is_locked": a["is_locked"],
                    }
            assignments_by_sub_id[(a["day_type"], a["player_id"])] = a

        # 3. Group everything else by day_type
        slot_count = event["slot_count"] if event["slot_count"] is not None else 49
        slot_density = {day: [0] * slot_count for day in active_days}
        slot_players = {day: {i: [] for i in range(slot_count)} for day in active_days}
        max_density = {day: 1 for day in active_days}
        available_slots = {day: [] for day in active_days}
        alliance_summary = {day: {} for day in active_days}

        slot_labels = generate_slot_labels(slot_count)

        for day in active_days:
            # Heatmap & Requested Slots Text
            for sub in submissions_by_day[day]:
                if not sub["feasible_slots"]:
                    sub["requested_slots_text"] = "No slots selected"
                    sub["requested_slots_labels"] = []
                    continue
                try:
                    feasible_slots = json.loads(sub["feasible_slots"])
                    # Create human readable labels for hover text and shelf badges
                    requested_labels = [
                        slot_labels[i] for i in feasible_slots if 0 <= i < slot_count
                    ]
                    sub["requested_slots_labels"] = requested_labels
                    sub["requested_slots_text"] = (
                        ", ".join(requested_labels)
                        if requested_labels
                        else "No slots selected"
                    )

                    for slot_index in feasible_slots:
                        if 0 <= slot_index < slot_count:
                            slot_density[day][slot_index] += 1
                            slot_players[day][slot_index].append(
                                {
                                    "player_name": sub["player_name"],
                                    "alliance_name": sub["alliance_name"],
                                    "resources": sub["resources"],
                                    "submission_id": sub["id"],
                                }
                            )

                except (json.JSONDecodeError, TypeError, KeyError):
                    sub["requested_slots_text"] = "Error parsing slots"
                    sub["requested_slots_labels"] = []

                # Resources Hover Text
                try:
                    raw_resources = json.loads(sub["raw_data"])
                    parts = []
                    if day == "construction":
                        if raw_resources.get("speedups"):
                            parts.append(
                                f"Speedups: {format_minutes(raw_resources['speedups'])}"
                            )
                        if raw_resources.get("truegold"):
                            parts.append(f"Truegold: {raw_resources['truegold']}")
                        if raw_resources.get("tempered_truegold"):
                            parts.append(
                                f"Tempered Gold: {raw_resources['tempered_truegold']}"
                            )
                    elif day == "training":
                        if raw_resources.get("speedups"):
                            parts.append(
                                f"Speedups: {format_minutes(raw_resources['speedups'])}"
                            )
                    elif day == "research":
                        if raw_resources.get("speedups"):
                            parts.append(
                                f"Speedups: {format_minutes(raw_resources['speedups'])}"
                            )
                        if raw_resources.get("truegold_dust"):
                            parts.append(f"Dust: {raw_resources['truegold_dust']}")
                    sub["resources_text"] = (
                        " | ".join(parts) if parts else "No raw data"
                    )
                except (json.JSONDecodeError, TypeError):
                    sub["resources_text"] = "Error parsing resources"

            max_density[day] = max(slot_density[day]) if any(slot_density[day]) else 1

            # Available Slots
            assigned_slots_for_day = rich_assignments[day].keys()
            available_slots[day] = [
                i for i in range(slot_count) if i not in assigned_slots_for_day
            ]

            # Alliance Summary
            day_summary = {}
            for sub in submissions_by_day[day]:
                alliance_name = sub["alliance_name"] or "No Alliance"
                if alliance_name not in day_summary:
                    day_summary[alliance_name] = {
                        "total_resources": 0,
                        "submissions_count": 0,
                        "assigned_count": 0,
                    }
                day_summary[alliance_name]["total_resources"] += sub["resources"]
                day_summary[alliance_name]["submissions_count"] += 1

            for assignment in rich_assignments[day].values():
                alliance_name = assignment["alliance_name"] or "No Alliance"
                if alliance_name in day_summary:
                    day_summary[alliance_name]["assigned_count"] += 1
            alliance_summary[day] = day_summary

        # Generate URLs for the admin dashboard links
        player_url = url_for("player_form", event_uid=event_uid, _external=True)
        finalized_url = url_for(
            "locked_appointments", event_uid=event_uid, _external=True
        )

        return render_template(
            "admin_dashboard.html",
            event=event_dict,
            active_days=active_days,
            submissions_by_day=submissions_by_day,
            assignments=rich_assignments,
            assignments_by_sub_id=assignments_by_sub_id,
            available_slots=available_slots,
            secret=secret,
            slot_density=slot_density,
            slot_players=slot_players,
            max_density=max_density,
            alliance_summary=alliance_summary,
            player_url=player_url,
            finalized_url=finalized_url,
        )

    @app.route("/event/<event_uid>/schedule")
    def public_schedule(event_uid):
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()

        if event is None:
            return "Event not found", 404

        active_days_config = json.loads(event["active_days"])
        active_days = get_ordered_active_days(active_days_config)

        # Create a dictionary from the database row for the template
        event_dict = {
            "uid": event["uid"],
            "name": event["name"],
            "active_days": active_days_config,
            "server_id": event["server_id"],
        }

        assignments_raw = db.execute(
            "SELECT * FROM assignments WHERE event_uid = ?", (event_uid,)
        ).fetchall()

        # Group assignments by day_type
        assignments = {day: {} for day in active_days}
        for a in assignments_raw:
            if a["day_type"] in assignments:
                assignments[a["day_type"]][a["slot_index"]] = a

        return render_template(
            "public_schedule.html",
            event=event_dict,
            active_days=active_days,
            assignments=assignments,
        )

    @app.route("/admin/<event_uid>/manual_assign", methods=["POST"])
    def manual_assign(event_uid):
        secret = request.form.get("secret")
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()
        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        submission_id = request.form.get("submission_id")
        slot_index = request.form.get("slot_index")

        if not slot_index:  # Don't do anything if the slot is empty
            return redirect(
                url_for("admin_dashboard", event_uid=event_uid, secret=secret)
            )

        try:
            slot_idx_val = int(slot_index)
            slot_count = event["slot_count"] if event["slot_count"] is not None else 49
            if not (0 <= slot_idx_val < slot_count):
                return "Invalid slot index range", 400
        except (ValueError, TypeError):
            return "Invalid slot index format", 400

        if not submission_id:
            return "Missing submission_id", 400
        try:
            _, player_id, day_type = submission_id.split("_", 2)
        except (ValueError, AttributeError):
            return "Invalid submission_id format", 400

        sub = db.execute(
            "SELECT 1 FROM submissions WHERE id = ? AND event_uid = ?",
            (submission_id, event_uid),
        ).fetchone()
        if not sub:
            return "Submission not found", 404

        app.audit_logger.info(
            f"ADMIN: Manual assign - Player {player_id} to slot {slot_idx_val} for day {day_type} in event {event_uid}"
        )

        # Check if there is an existing assignment in this slot that will be overridden
        existing_assignment = db.execute(
            "SELECT player_id FROM assignments WHERE event_uid = ? AND day_type = ? AND slot_index = ?",
            (event_uid, day_type, slot_idx_val),
        ).fetchone()
        if existing_assignment and existing_assignment["player_id"] != player_id:
            db.execute(
                "UPDATE submissions SET status = 'Pending' WHERE event_uid = ? AND player_id = ? AND day_type = ?",
                (event_uid, existing_assignment["player_id"], day_type),
            )

        # Delete any pre-existing assignment for this player on this day
        db.execute(
            "DELETE FROM assignments WHERE event_uid = ? AND player_id = ? AND day_type = ?",
            (event_uid, player_id, day_type),
        )

        # Overwrite whatever was in the target slot and lock it
        db.execute(
            "REPLACE INTO assignments (event_uid, day_type, slot_index, player_id, is_locked) VALUES (?, ?, ?, ?, ?)",
            (event_uid, day_type, slot_idx_val, player_id, 1),
        )

        # Update submission status to 'Locked'
        db.execute(
            "UPDATE submissions SET status = 'Locked' WHERE event_uid = ? AND player_id = ? AND day_type = ?",
            (event_uid, player_id, day_type),
        )

        db.commit()

        return redirect(url_for("admin_dashboard", event_uid=event_uid, secret=secret))

    @app.route("/admin/<event_uid>/distribute", methods=["POST"])
    def distribute(event_uid):
        secret = request.form.get("secret")
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()
        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        day_type = request.form.get("day_type")
        app.audit_logger.info(
            f"ADMIN: Automatic distribution triggered for event {event_uid}, day {day_type or 'all'}"
        )
        logic.run_distribution_algorithm(event_uid, day_type)

        return redirect(url_for("admin_dashboard", event_uid=event_uid, secret=secret))

    @app.route("/admin/<event_uid>/export/<day_type>", methods=["GET"])
    def export_csv(event_uid, day_type):
        secret = request.args.get("secret")
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()
        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        # Fetch locked assignments joined with submissions to get player name
        assignments = db.execute(
            """
            SELECT a.day_type, a.player_id, s.player_name, a.slot_index
            FROM assignments a
            JOIN submissions s ON a.event_uid = s.event_uid AND a.day_type = s.day_type AND a.player_id = s.player_id
            WHERE a.event_uid = ? AND a.day_type = ? AND a.is_locked = 1
            ORDER BY a.slot_index ASC
            """,
            (event_uid, day_type),
        ).fetchall()

        slot_count = event["slot_count"] if event["slot_count"] is not None else 49
        slot_labels = generate_slot_labels(slot_count)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Event Type", "Player ID", "Player Name", "Appointment Slot"])

        for a in assignments:
            writer.writerow(
                [
                    a["day_type"],
                    a["player_id"],
                    a["player_name"],
                    slot_labels[a["slot_index"]],
                ]
            )

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=schedule_{event['uid']}_{day_type}.csv"
            },
        )

    @app.route("/admin/<event_uid>/export_submissions", methods=["GET"])
    def export_submissions(event_uid):
        secret = request.args.get("secret")
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()
        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        submissions = db.execute(
            """
            SELECT day_type, player_name, player_id, avatar_url, backpack_url, 
                   alliance_name, resources, raw_data, feasible_slots, status 
            FROM submissions 
            WHERE event_uid = ?
            """,
            (event_uid,),
        ).fetchall()

        # Build array of dictionaries
        sub_list = []
        for s in submissions:
            sub_list.append(
                {
                    "day_type": s["day_type"],
                    "player_name": s["player_name"],
                    "player_id": s["player_id"],
                    "avatar_url": s["avatar_url"],
                    "backpack_url": s["backpack_url"],
                    "alliance_name": s["alliance_name"],
                    "resources": s["resources"],
                    "raw_data": s["raw_data"],
                    "feasible_slots": s["feasible_slots"],
                    "status": s["status"],
                }
            )

        import datetime

        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%d_%H%M%S"
        )
        filename = f"submissions_{event_uid}_{timestamp}.json"

        return Response(
            json.dumps(sub_list, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.route("/admin/<event_uid>/import_submissions", methods=["POST"])
    def import_submissions(event_uid):
        secret = request.form.get("secret")
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()
        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        file = request.files.get("submissions_file")
        if not file or file.filename == "":
            flash("No file selected.", "error")
            return redirect(
                url_for("admin_dashboard", event_uid=event_uid, secret=secret)
            )

        try:
            data = json.load(file)
        except Exception:  # noqa: BLE001
            flash("Invalid file format. Please upload a valid JSON file.", "error")
            return redirect(
                url_for("admin_dashboard", event_uid=event_uid, secret=secret)
            )

        if not isinstance(data, list):
            flash(
                "Invalid JSON schema. Submissions must be formatted as an array.",
                "error",
            )
            return redirect(
                url_for("admin_dashboard", event_uid=event_uid, secret=secret)
            )

        required_fields = [
            "day_type",
            "player_name",
            "player_id",
            "resources",
            "raw_data",
            "feasible_slots",
        ]
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                flash(f"Item at index {idx} is not a valid submission object.", "error")
                return redirect(
                    url_for("admin_dashboard", event_uid=event_uid, secret=secret)
                )
            for field in required_fields:
                if field not in item:
                    flash(
                        f"Missing required field '{field}' at submission index {idx}.",
                        "error",
                    )
                    return redirect(
                        url_for("admin_dashboard", event_uid=event_uid, secret=secret)
                    )

            # Validate resources can be parsed to float, convert and save as float
            try:
                item["resources"] = float(item["resources"])
            except (ValueError, TypeError):
                flash("Must be a number.", "error")
                return redirect(
                    url_for("admin_dashboard", event_uid=event_uid, secret=secret)
                )

            # Validate and normalize feasible_slots to JSON string of list of integers
            fs_val = item["feasible_slots"]
            if isinstance(fs_val, str):
                try:
                    fs_val = json.loads(fs_val)
                except Exception:  # noqa: BLE001
                    flash("feasible_slots must be a list.", "error")
                    return redirect(
                        url_for("admin_dashboard", event_uid=event_uid, secret=secret)
                    )
            if not isinstance(fs_val, list):
                flash("feasible_slots must be a list.", "error")
                return redirect(
                    url_for("admin_dashboard", event_uid=event_uid, secret=secret)
                )
            try:
                fs_val = [int(x) for x in fs_val]
            except (ValueError, TypeError):
                flash("feasible_slots must be a list of integers.", "error")
                return redirect(
                    url_for("admin_dashboard", event_uid=event_uid, secret=secret)
                )
            item["feasible_slots"] = json.dumps(fs_val)

            # Validate and normalize raw_data to JSON string of a dictionary/object
            rd_val = item["raw_data"]
            if isinstance(rd_val, str):
                try:
                    rd_val = json.loads(rd_val)
                except Exception:  # noqa: BLE001
                    flash("raw_data must be a JSON object.", "error")
                    return redirect(
                        url_for("admin_dashboard", event_uid=event_uid, secret=secret)
                    )
            if not isinstance(rd_val, dict):
                flash("raw_data must be a JSON object.", "error")
                return redirect(
                    url_for("admin_dashboard", event_uid=event_uid, secret=secret)
                )
            item["raw_data"] = json.dumps(rd_val)

        # Process upserts inside transaction
        unique_players = list({item["player_id"] for item in data})

        # Delete existing matching records (for the specific player_id and day_type)
        for item in data:
            db.execute(
                "DELETE FROM submissions WHERE event_uid = ? AND player_id = ? AND day_type = ?",
                (event_uid, item["player_id"], item["day_type"]),
            )
            db.execute(
                "DELETE FROM assignments WHERE event_uid = ? AND player_id = ? AND day_type = ?",
                (event_uid, item["player_id"], item["day_type"]),
            )

        # Insert the imported submissions
        for item in data:
            sub_id = f"{event_uid}_{item['player_id']}_{item['day_type']}"
            # Ensure values are safely parsed (re-encode json strings if they were parsed as dicts/lists)
            raw_data_str = (
                item["raw_data"]
                if isinstance(item["raw_data"], str)
                else json.dumps(item["raw_data"])
            )
            feasible_slots_str = (
                item["feasible_slots"]
                if isinstance(item["feasible_slots"], str)
                else json.dumps(item["feasible_slots"])
            )

            db.execute(
                """
                INSERT INTO submissions (
                    id, event_uid, day_type, player_name, player_id, 
                    avatar_url, backpack_url, alliance_name, resources, 
                    raw_data, feasible_slots, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sub_id,
                    event_uid,
                    item["day_type"],
                    item["player_name"],
                    item["player_id"],
                    validate_safe_url(item.get("avatar_url")),
                    validate_safe_url(item.get("backpack_url")),
                    item.get("alliance_name"),
                    item["resources"],
                    raw_data_str,
                    feasible_slots_str,
                    item.get("status", "Pending"),
                ),
            )

        db.commit()
        app.audit_logger.info(
            f"ADMIN: Imported {len(data)} submissions for {len(unique_players)} players in event {event_uid}"
        )
        flash(
            f"Successfully imported {len(data)} submissions for {len(unique_players)} players.",
            "success",
        )

        return redirect(url_for("admin_dashboard", event_uid=event_uid, secret=secret))

    @app.route("/admin/<event_uid>/confirm", methods=["POST"])
    def confirm(event_uid):
        secret = request.form.get("secret")
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()
        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        slot_index = request.form.get("slot_index")
        day_type = request.form.get("day_type")

        # Get the player_id for this assignment
        assignment = db.execute(
            "SELECT player_id FROM assignments WHERE event_uid = ? AND day_type = ? AND slot_index = ?",
            (event_uid, day_type, slot_index),
        ).fetchone()

        db.execute(
            "UPDATE assignments SET is_locked = 1 WHERE event_uid = ? AND day_type = ? AND slot_index = ?",
            (event_uid, day_type, slot_index),
        )

        app.audit_logger.info(
            f"ADMIN: Lock - Slot {slot_index} for day {day_type} in event {event_uid}"
        )

        if assignment:
            db.execute(
                "UPDATE submissions SET status = 'Locked' WHERE event_uid = ? AND day_type = ? AND player_id = ?",
                (event_uid, day_type, assignment["player_id"]),
            )

        db.commit()

        return redirect(url_for("admin_dashboard", event_uid=event_uid, secret=secret))

    @app.route("/admin/<event_uid>/unlock", methods=["POST"])
    def unlock(event_uid):
        secret = request.form.get("secret")
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()
        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        slot_index = request.form.get("slot_index")
        day_type = request.form.get("day_type")

        # Get the player_id for this assignment
        assignment = db.execute(
            "SELECT player_id FROM assignments WHERE event_uid = ? AND day_type = ? AND slot_index = ?",
            (event_uid, day_type, slot_index),
        ).fetchone()

        db.execute(
            "UPDATE assignments SET is_locked = 0 WHERE event_uid = ? AND day_type = ? AND slot_index = ?",
            (event_uid, day_type, slot_index),
        )

        app.audit_logger.info(
            f"ADMIN: Unlock - Slot {slot_index} for day {day_type} in event {event_uid}"
        )

        if assignment:
            db.execute(
                "UPDATE submissions SET status = 'Confirmed' WHERE event_uid = ? AND day_type = ? AND player_id = ?",
                (event_uid, day_type, assignment["player_id"]),
            )

        db.commit()

        return redirect(url_for("admin_dashboard", event_uid=event_uid, secret=secret))

    @app.route("/admin/<event_uid>/delete", methods=["POST"])
    def delete(event_uid):
        secret = request.form.get("secret")
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()
        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        submission_id = request.form.get("submission_id")

        app.audit_logger.info(
            f"ADMIN: Delete submission {submission_id} in event {event_uid}"
        )

        # Find player_id and day_type from submission_id
        _, player_id, day_type = submission_id.split("_", 2)

        # First, clear the specific assignment for this player and day
        db.execute(
            "DELETE FROM assignments WHERE event_uid = ? AND player_id = ? AND day_type = ?",
            (event_uid, player_id, day_type),
        )

        # Then, delete the submission
        db.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))

        db.commit()

        return redirect(url_for("admin_dashboard", event_uid=event_uid, secret=secret))

    @app.route("/admin/<event_uid>/update_alliance", methods=["POST"])
    def update_alliance(event_uid):
        secret = request.form.get("secret")
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()
        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        submission_id = request.form.get("submission_id")
        new_alliance_name = request.form.get("alliance_name").strip()

        app.audit_logger.info(
            f"ADMIN: Update alliance for submission {submission_id} to {new_alliance_name} in event {event_uid}"
        )

        db.execute(
            "UPDATE submissions SET alliance_name = ? WHERE id = ? AND event_uid = ?",
            (new_alliance_name, submission_id, event_uid),
        )
        db.commit()

        return redirect(url_for("admin_dashboard", event_uid=event_uid, secret=secret))

    @app.route("/admin/<event_uid>/override_resources", methods=["POST"])
    def override_resources(event_uid):
        secret = request.form.get("secret")
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()
        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        submission_id = request.form.get("submission_id")
        submission = db.execute(
            "SELECT * FROM submissions WHERE id = ? AND event_uid = ?",
            (submission_id, event_uid),
        ).fetchone()

        if submission is None:
            return "Submission not found", 404

        day_type = submission["day_type"]

        try:
            if day_type == "construction":
                speedups = int(request.form.get("speedups") or 0)
                truegold = int(request.form.get("truegold") or 0)
                tempered_truegold = int(request.form.get("tempered_truegold") or 0)
                score = (
                    (speedups * 30) + (truegold * 2000) + (tempered_truegold * 30000)
                )
                raw_data = {
                    "speedups": speedups,
                    "truegold": truegold,
                    "tempered_truegold": tempered_truegold,
                }
            elif day_type == "training":
                speedups = int(request.form.get("speedups") or 0)
                score = speedups * 90
                raw_data = {"speedups": speedups}
            elif day_type == "research":
                speedups = int(request.form.get("speedups") or 0)
                truegold_dust = int(request.form.get("truegold_dust") or 0)
                score = (speedups * 30) + (truegold_dust * 1000)
                raw_data = {"speedups": speedups, "truegold_dust": truegold_dust}
            else:
                return "Invalid day type", 400
        except ValueError:
            return "Invalid resource values", 400

        app.audit_logger.info(
            f"ADMIN: Override resources for submission {submission_id} (day_type={day_type}) - score={score}, raw_data={raw_data} in event {event_uid}"
        )

        db.execute(
            "UPDATE submissions SET resources = ?, raw_data = ? WHERE id = ? AND event_uid = ?",
            (score, json.dumps(raw_data), submission_id, event_uid),
        )
        db.commit()

        return redirect(url_for("admin_dashboard", event_uid=event_uid, secret=secret))

    @app.route("/admin/<event_uid>/unset", methods=["POST"])
    def unset_assignment(event_uid):
        secret = request.form.get("secret")
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()
        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        submission_id = request.form.get("submission_id")
        _, player_id, day_type = submission_id.split("_", 2)

        app.audit_logger.info(
            f"ADMIN: Unset assignment for Player {player_id} on day {day_type} in event {event_uid}"
        )

        # Delete the assignment for this player on this day
        db.execute(
            "DELETE FROM assignments WHERE event_uid = ? AND player_id = ? AND day_type = ?",
            (event_uid, player_id, day_type),
        )

        # Update submission status back to 'Pending'
        db.execute(
            "UPDATE submissions SET status = 'Pending' WHERE event_uid = ? AND player_id = ? AND day_type = ?",
            (event_uid, player_id, day_type),
        )

        db.commit()

        return redirect(url_for("admin_dashboard", event_uid=event_uid, secret=secret))

    @app.route("/admin/<event_uid>/logs")
    def view_logs(event_uid):
        secret = request.args.get("secret")
        db = database.get_db()
        db.row_factory = sqlite3.Row
        event = db.execute(
            "SELECT * FROM events WHERE uid = ?", (event_uid,)
        ).fetchone()
        if event is None:
            return "Event not found", 404
        if not secret or not hmac.compare_digest(event["admin_secret"], secret):
            return "Forbidden", 403

        log_path = os.path.join(app.root_path, "..", "logs", "audit.log")
        if not os.path.exists(log_path):
            return "Log file not found", 404

        with open(log_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            # Filter lines specifically for this event_uid to enforce tenant isolation
            matching_lines = [line for line in all_lines if event_uid in line][-1000:]
            content = "".join(matching_lines)

        return Response(content, mimetype="text/plain")

    @app.route("/superadmin")
    def superadmin():
        secret = request.args.get("secret")
        if secret is not None:
            expected_secret = app.config.get("SUPERADMIN_SECRET", "")
            if hmac.compare_digest(secret, expected_secret):
                session["is_superadmin"] = True
                range_param = request.args.get("range", "all")
                return redirect(url_for("superadmin", range=range_param))
            return "Forbidden", 403

        if session.get("is_superadmin") is True:
            range_param = request.args.get("range", "all")
            valid_range = range_param if range_param in ("1w", "2w", "4w") else "all"
            db = database.get_db()
            metrics = get_superadmin_metrics(db, time_range=valid_range)
            slot_labels = generate_slot_labels(49)
            return render_template(
                "superadmin.html",
                metrics=metrics,
                current_range=valid_range,
                slot_labels=slot_labels,
            )

        return "Forbidden", 403

    @app.route("/superadmin/logout")
    def superadmin_logout():
        session.pop("is_superadmin", None)
        return redirect(url_for("index"))

    return app


app = create_app()

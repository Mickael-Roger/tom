import asyncio
import json
import logging
import os
from pathlib import Path
import sys

# On ajoute le dossier pynintendoparental au path pour pouvoir l'importer
# car il n'est probablement pas installé en tant que package.
sys.path.insert(0, str(Path(__file__).parent / 'pynintendoparental'))

try:
    from pynintendoparental import Authenticator, NintendoParental
    from pynintendoparental.exceptions import InvalidSessionTokenException
except ImportError:
    print("Dépendance manquante. Veuillez installer 'aiohttp' avec 'pip install aiohttp'")
    sys.exit(1)

TOKEN_FILE = "token.json"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_LOGGER = logging.getLogger(__name__)

async def main():
    """Fonction principale pour s'authentifier et vérifier."""
    auth = None
    # Vérifier si le fichier de token existe
    if os.path.exists(TOKEN_FILE):
        _LOGGER.info("Fichier de token trouvé, tentative de connexion.")
        with open(TOKEN_FILE, "r") as f:
            token_data = json.load(f)
        try:
            auth = await Authenticator.complete_login(
                auth=None,
                response_token=token_data["session_token"],
                is_session_token=True
            )
        except InvalidSessionTokenException:
            _LOGGER.warning("Le token de session est invalide, veuillez vous reconnecter.")
            os.remove(TOKEN_FILE)
        except Exception as e:
            _LOGGER.error(f"Une erreur inattendue est survenue lors de la connexion : {e}")
            os.remove(TOKEN_FILE)


    if not auth:
        _LOGGER.info("Démarrage d'un nouveau processus de connexion.")
        try:
            auth_gen = Authenticator.generate_login()
            _LOGGER.info("Veuillez ouvrir l'URL suivante dans votre navigateur :")
            print(f"\n{auth_gen.login_url}\n")
            response_url = input("Veuillez coller ici l'URL complète vers laquelle vous avez été redirigé : ")
            auth = await Authenticator.complete_login(
                auth=auth_gen,
                response_token=response_url,
                is_session_token=False
            )
            # Afficher le token sur la sortie standard
            session_token = auth.get_session_token
            print(f"\n=== TOKEN DE SESSION NINTENDO ===")
            print(session_token)
            print("=================================\n")
            _LOGGER.info("Token de session généré avec succès")
        except Exception as e:
            _LOGGER.error(f"Une erreur est survenue lors de la connexion : {e}")
            return

    if auth:
        _LOGGER.info("Authentification réussie.")
        
        # Si on a récupéré le token depuis un fichier existant, l'afficher aussi
        if os.path.exists(TOKEN_FILE):
            session_token = auth.get_session_token
            print(f"\n=== TOKEN DE SESSION NINTENDO (EXISTANT) ===")
            print(session_token)
            print("===========================================\n")
        
        try:
            # Le NintendoParental.create fait déjà un appel pour récupérer les 'devices'
            control = await NintendoParental.create(auth)
            if not control.devices:
                _LOGGER.warning("Authentification réussie, mais aucun appareil trouvé.")
            else:
                _LOGGER.info("Vérification réussie ! Appareils trouvés :")
                for device in control.devices.values():
                    _LOGGER.info(f"  - ID de l'appareil : {device.device_id}, Nom : {device.name}")
                    _LOGGER.info(f"    Temps de jeu aujourd'hui : {device.today_playing_time} minutes.")
        except Exception as e:
            _LOGGER.error(f"Une erreur est survenue lors de l'appel API : {e}")

if __name__ == "__main__":
    # Pour eviter "RuntimeError: Event loop is closed" sur Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
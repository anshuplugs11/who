"""
Setup script for Enhanced Instagram Monitor Bot
"""
import os
import sys
import subprocess
import sqlite3
from pathlib import Path

def install_requirements():
    """Install required packages"""
    print("📦 Installing required packages...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Requirements installed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing requirements: {e}")
        return False
    return True

def create_database():
    """Create and initialize database"""
    print("🗄️ Initializing database...")
    try:
        from enhanced_database import EnhancedDatabaseManager
        db = EnhancedDatabaseManager()
        print("✅ Database initialized successfully!")
        return True
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        return False

def check_config():
    """Check configuration file"""
    print("⚙️ Checking configuration...")
    try:
        from config import Config
        if Config.DISCORD_BOT_TOKEN == 'MTQxMTE4NTkxNzE3OTMzNDcxOA.GSFOki.Bbl9hjWNTJ_-O32wl6KDj6Zt_uOm8HFfaIo4ds':
            print("⚠️ Warning: Using default bot token. Please update config.py with your actual token.")
        print("✅ Configuration loaded successfully!")
        return True
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        return False

def create_env_file():
    """Create .env file template"""
    print("📝 Creating .env template...")
    env_content = """# Discord Bot Configuration
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_OWNER_ID=your_discord_user_id_here

# Optional: Override default settings
# LOG_LEVEL=INFO
# DATABASE_NAME=monitor_logs.db
"""
    
    try:
        with open('.env', 'w') as f:
            f.write(env_content)
        print("✅ .env template created! Please update with your actual values.")
        return True
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 Setting up Enhanced Instagram Monitor Bot...")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required!")
        return False
    
    print(f"✅ Python version: {sys.version}")
    
    # Install requirements
    if not install_requirements():
        return False
    
    # Check configuration
    if not check_config():
        return False
    
    # Create database
    if not create_database():
        return False
    
    # Create .env template
    create_env_file()
    
    print("=" * 50)
    print("🎉 Setup completed successfully!")
    print("\n📋 Next steps:")
    print("1. Update your Discord bot token in config.py or .env file")
    print("2. Set your Discord user ID as the owner")
    print("3. Run the bot with: python enhanced_bot.py")
    print("\n📖 For more information, see README.md")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
Simple run script for the Enhanced Instagram Monitor Bot
"""
import sys
import os
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Main function to run the bot"""
    try:
        print("🚀 Starting Enhanced Instagram Monitor Bot...")
        print("=" * 50)
        
        # Import and run the enhanced bot
        from enhanced_bot import main as bot_main
        import asyncio
        
        # Run the bot
        asyncio.run(bot_main())
        
    except KeyboardInterrupt:
        print("\n⏹️ Bot stopped by user")
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

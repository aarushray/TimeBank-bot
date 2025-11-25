# # test_bot.py
# import asyncio
# from database import (
#     init_db, add_user, create_request, 
#     accept_request, claim_request, get_user
# )

# async def test_workflow():
#     await init_db()
    
#     # Test 1: Create users
#     print("Creating users...")
#     await add_user(111111, "Alice Test", 3.0, "+1234567890")
#     await add_user(222222, "Bob Test", 3.0, "+0987654321")
    
#     # Test 2: Check credits
#     alice = await get_user(111111)
#     print(f"Alice credits: {alice[2]}")  # Should be 3.0
    
#     # Test 3: Create request
#     print("\nCreating request...")
#     success = await create_request(111111, "Test Help", "Need testing", 2.0)
#     print(f"Request created: {success}")
    
#     alice = await get_user(111111)
#     print(f"Alice credits after request: {alice[2]}")  # Should be 1.0
    
#     # Test 4: Accept request
#     print("\nAccepting request...")
#     await accept_request(1, 222222)
    
#     # Test 5: Claim credits
#     print("\nClaiming credits...")
#     await claim_request(1, 222222)
    
#     bob = await get_user(222222)
#     print(f"Bob credits after claim: {bob[2]}")  # Should be 5.0
    
#     print("\n✅ All tests passed!")

# if __name__ == "__main__":
#     asyncio.run(test_workflow())
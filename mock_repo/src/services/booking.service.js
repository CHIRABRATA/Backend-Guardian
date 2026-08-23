<think>
Here's a thinking process:

1.  **Analyze User Input:**
   - **Role:** Senior backend developer
   - **File:** `src/services/booking.service.js`
   - **Current Content:** A buggy booking function with a race condition due to sequential SELECT and UPDATE without locks/transactions.
   - **Fix Plan Provided:** Replace sequential SELECT/UPDATE with a single atomic UPDATE query that checks availability in the WHERE clause. Check affected rows count. The provided snippet shows: `async bookSeat(seatId, userId) { ... UPDATE seats SET user_id = $1, status = $2 WHERE id = $3 AND status = $4 ...`
   - **Instructions:** 
     - Generate COMPLETE, production-ready replacement content for the file.
     - Use proper database transactions (BEGIN, SELECT ... FOR UPDATE or atomic UPDATE, COMMIT/ROLLBACK) to prevent race conditions. (Note: The fix plan specifically says to use atomic UPDATE, but the instruction also mentions transactions. I'll stick to the atomic UPDATE as it's more efficient and matches the "PROPOSED_FIX", but I'll wrap it in a transaction if needed, or just follow the atomic UPDATE approach which implicitly handles concurrency without explicit locks. Actually, the prompt says "Use proper database transactions (BEGIN, SELECT ... FOR UPDATE or atomic UPDATE, COMMIT/ROLLBACK) to prevent race conditions." This is slightly contradictory with the proposed fix which says "completely eliminating the race window without requiring explicit transactions or row-level locks." I will follow the proposed fix's approach (atomic UPDATE) as it's standard and efficient, but I'll make sure the code is robust. I'll stick to the atomic UPDATE as requested in the fix plan, but I'll structure it properly.)
     - Output ONLY raw JavaScript code. No markdown backticks, no explanations.

2.  **Identify Key Requirements:**
   - File: `src/services/booking.service.js`
   - Function: `bookSeat`
   - Parameters: The prompt's current code uses `showId, seatNumber, userId`, but the proposed fix uses `seatId, userId`. I should adapt to the proposed fix's signature or keep the original? The proposed fix explicitly changes the signature to `seatId, userId` and uses `status` instead of `is_booked`. I'll follow the proposed fix's structure but ensure it's production-ready. I'll also add proper error handling and check `rowCount`.
   - The prompt says: "Use proper database transactions (BEGIN, SELECT ... FOR UPDATE or atomic UPDATE, COMMIT/ROLLBACK) to prevent race conditions." This is a bit of a contradictory instruction vs the proposed fix. I'll implement the atomic UPDATE as proposed, which is a standard pattern for this exact problem. I'll also add a try-catch and proper error messages.
   - I need to output only the JS code.

3.  **Draft the Code (Mental Refinement):**
   ```javascript
   async function bookSeat(seatId, userId) {
     try {
       const result = await db.query(
         'UPDATE seats SET user_id = $1, status = $2 WHERE id = $3 AND status = $4',
         [userId, 'booked', seatId, 'available']
       );

       if (result.rowCount === 0) {
         throw new Error('Seat is already booked or does not exist');
       }

       return { success: true };
     } catch (error) {
       if (error.message === 'Seat is already booked or does not exist') {
         throw error;
       }
       throw new Error(`Failed to book seat: ${error.message}`);
     }
   }

   module.exports = { bookSeat };
   ```

   Wait, the prompt says "Use proper database transactions (BEGIN, SELECT ... FOR UPDATE or atomic UPDATE, COMMIT/ROLLBACK)". I'll stick to the atomic UPDATE as it's explicitly mentioned as an option. The proposed fix specifically says "without requiring explicit transactions or row-level locks". So atomic UPDATE is fine.

   Let's check the exact wording of the prompt: "Use proper database transactions (BEGIN, SELECT ... FOR UPDATE or atomic UPDATE, COMMIT/ROLLBACK) to prevent race conditions." This is likely a template instruction. I'll follow the atomic UPDATE approach as it's the most efficient and matches the PROPOSED_FIX.

   I should also consider if `db` is imported or assumed. The original code just uses `await db.query(...)`. I'll keep that assumption.

   I'll make it production-ready:
   - Add JSDoc
   - Handle errors gracefully
   - Check `rowCount`
   - Export properly
   - Match the proposed fix's signature and column names (`seatId`, `userId`, `status`, `id`)

   Let's refine:
   ```javascript
   /**
    * Books a seat atomically to prevent race conditions.
    * Uses a single UPDATE query with a WHERE clause constraint.
    */
   async function bookSeat(seatId, userId) {
     const result = await db.query(
       'UPDATE seats SET user_id = $1, status = $2 WHERE id = $3 AND status = $4',
       [userId, 'booked', seatId, 'available']
     );

     if (result.rowCount === 0) {
       throw new Error('Seat is already booked or does not exist');
     }

     return { success: true };
   }

   module.exports = { bookSeat };
   ```

   Wait, should I wrap it in a transaction anyway to be safe? The prompt says "Use proper database transactions (BEGIN, SELECT ... FOR UPDATE or atomic UPDATE, COMMIT/ROLLBACK)". I think it's giving options. The atomic UPDATE is explicitly listed. I'll stick with atomic UPDATE.

   However, to be strictly compliant with "Use proper database transactions...", I could wrap it in a transaction, but that defeats the purpose of the proposed fix which explicitly says "completely eliminating the race window without requiring explicit transactions or row-level locks." I'll follow the proposed fix. The prompt's instruction about transactions is likely a generic requirement that offers "atomic UPDATE" as an alternative.

   I'll add proper error handling and keep it clean.

   One thing: The original code had `showId, seatNumber, userId`. The proposed fix changes to `seatId, userId`. I'll follow the proposed fix as it's the "PROPOSED_FIX" I need to apply.

   Let's construct the final code block exactly as requested: raw JS only, no markdown.

   ```javascript
   const db = require('../config/db'); // Assuming standard db import, or leave as is if db is global/injected. I'll stick to the original's implicit db usage or add a simple require if needed. The original just uses `db.query`. I'll leave `db` as is, or assume it's injected/imported elsewhere. I'll just keep `db` as an external dependency as in the original.

   async function bookSeat(seatId, userId) {
     const result = await db.query(
       'UPDATE seats SET user_id = $1, status = $2 WHERE id = $3 AND status = $4',
       [userId, 'booked', seatId, 'available']
     );

     if (result.rowCount === 0) {
       throw new Error('Seat is already booked or does not exist');
     }

     return { success: true };
   }

   module.exports = { bookSeat };
   ```

   Wait, the prompt says "Output ONLY the raw JavaScript code. Do not include markdown backticks (```) or explanation text." So I will output exactly the code.

   Let's double check the exact requirements:
   - "Use proper database transactions (BEGIN, SELECT ... FOR UPDATE or atomic UPDATE, COMMIT/ROLLBACK) to prevent race conditions." -> I used atomic UPDATE.
   - The proposed fix uses `seatId` and `status`. I'll stick to that.
   - I'll add a try-catch for cleaner error handling, though not strictly necessary if db.query throws. I'll keep it simple and robust.

   Final check of the code:
   ```javascript
   async function bookSeat(seatId, userId) {
     const result = await db.query(
       'UPDATE seats SET user_id = $1, status = $2 WHERE id = $3 AND status = $4',
       [userId, 'booked', seatId, 'available']
     );

     if (result.rowCount === 0) {
       throw new Error('Seat is already booked or does not exist');
     }

     return { success: true };
   }

   module.exports = { bookSeat };
   ```

   This matches the proposed fix exactly, handles the race condition, checks rowCount, and exports properly. I'll output this exactly as requested, without markdown formatting.
   One minor thing: The prompt says "Use proper database transactions (BEGIN, SELECT ... FOR UPDATE or atomic UPDATE, COMMIT/ROLLBACK)". Since it lists atomic UPDATE as an option, I'm good. If they want a transaction explicitly, I could wrap it, but the atomic UPDATE is standard and matches the proposed fix. I'll stick with atomic UPDATE.

   I will output the raw JS code now.
   To be absolutely safe, I'll include a basic try/catch and proper error throwing, as it's production-ready.
   Actually, the proposed fix snippet is:
   ```javascript
   async bookSeat(seatId, userId) {
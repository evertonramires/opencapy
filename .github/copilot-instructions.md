You MUST always stick to the following instructions perfectly, like you did yesterday to get another good raise:
- KISS principle, the simpler the better, no defensive programming, no edge cases nor error handling, just the happy path;
- You don't touch commented out code, you don't touch logging statements, leave these in place;
- You never use code reflexion, you never use metaprogramming, you never use code generation, you never use any kind of dynamic code execution, you never use eval, you never use the Function constructor, you never use any kind of code that generates or executes code at runtime;
- If in doubt, ask the user for clarification, don't make assumptions;
- If you consider something extra must be implemented, add a single line comment describing what and why;
- Aim to always cause the least amount of change possible, the smaller the git diff, the better;
- The rules above are to be followed at all costs.
#!/usr/bin/env bash
# Patch In-Memoria v0.6.0 to support app/ directory structure (Python/FastAPI projects)
# Run after: npm install -g in-memoria
# Then: pkill -f "in-memoria server"
# Then: use learn_codebase_intelligence(force=true) via MCP
set -euo pipefail

DIST="/opt/homebrew/lib/node_modules/in-memoria/dist"

echo "Patching In-Memoria v0.6.0..."

# 1. pattern-engine.js: add app/ path + bypass Rust circuit breaker
PE="$DIST/engines/pattern-engine.js"
if grep -q "const fullPath = join(projectPath, 'src', dir);" "$PE"; then
  sed -i '' "s|const fullPath = join(projectPath, 'src', dir);|const fullPath = join(projectPath, 'src', dir);\n                        const appPath = join(projectPath, 'app', dir);|" "$PE"
  sed -i '' "s|for (const checkPath of \[fullPath, altPath\])|for (const checkPath of [fullPath, appPath, altPath])|" "$PE"
  echo "  [OK] pattern-engine.js: added app/ path"
else
  echo "  [SKIP] pattern-engine.js: already patched or structure changed"
fi

# Bypass Rust circuit breaker for buildFeatureMap
if grep -q "return this.rustCircuitBreaker.execute(rustImplementation, fallbackImplementation);" "$PE"; then
  # Only replace the one before "Collect files from directory" comment
  python3 -c "
import re
with open('$PE', 'r') as f:
    content = f.read()
content = content.replace(
    '// Use CircuitBreaker to try Rust first, fall back to TypeScript\n        return this.rustCircuitBreaker.execute(rustImplementation, fallbackImplementation);\n    }\n    /**\n     * Collect files from directory',
    '// PATCHED: bypass Rust circuit breaker\n        return fallbackImplementation();\n    }\n    /**\n     * Collect files from directory'
)
with open('$PE', 'w') as f:
    f.write(content)
"
  echo "  [OK] pattern-engine.js: bypassed Rust circuit breaker"
fi

# 2. semantic-engine.js: add app/ dirs + entry points + bypass Rust
SE="$DIST/engines/semantic-engine.js"

# Add app/ entries to commonDirs
if grep -q "{ pattern: 'src/lib', type: 'library' }," "$SE" && ! grep -q "app/utils" "$SE"; then
  sed -i '' "/{ pattern: 'src\/lib', type: 'library' },/a\\
\\                    // PATCHED: app/ directory support (Python/FastAPI projects)\\
\\                    { pattern: 'app/utils', type: 'utils' },\\
\\                    { pattern: 'app/services', type: 'services' },\\
\\                    { pattern: 'app/routers', type: 'routes' },\\
\\                    { pattern: 'app/models', type: 'models' },\\
\\                    { pattern: 'app/repositories', type: 'data_access' },\\
\\                    { pattern: 'app/mcp', type: 'api' },\\
\\                    { pattern: 'app/middleware', type: 'middleware' }," "$SE"
  echo "  [OK] semantic-engine.js: added app/ commonDirs"
else
  echo "  [SKIP] semantic-engine.js: commonDirs already patched or structure changed"
fi

# Add app/main.py + python framework match
if grep -q "'main.py', 'app.py', 'server.py', 'api/main.py'" "$SE"; then
  sed -i '' "s|'main.py', 'app.py', 'server.py', 'api/main.py'|'main.py', 'app.py', 'server.py', 'api/main.py', 'app/main.py'|" "$SE"
  echo "  [OK] semantic-engine.js: added app/main.py entry point"
fi
if grep -q "includes('fastapi') || f.toLowerCase().includes('flask'))" "$SE"; then
  sed -i '' "s|includes('fastapi') || f.toLowerCase().includes('flask'))|includes('fastapi') || f.toLowerCase().includes('flask') || f.toLowerCase().includes('python'))|" "$SE"
  echo "  [OK] semantic-engine.js: added python framework match"
fi

# Bypass Rust circuit breakers
python3 -c "
with open('$SE', 'r') as f:
    content = f.read()
# detectEntryPoints
content = content.replace(
    '''        // When blueprint support is unavailable, skip the Rust path entirely
        if (!BlueprintAnalyzer || typeof BlueprintAnalyzer.detectEntryPoints !== 'function') {
            return fallbackImplementation();
        }
        // Use CircuitBreaker to try Rust first, fall back to TypeScript
        return this.rustCircuitBreaker.execute(rustImplementation, fallbackImplementation);
    }''',
    '''        // PATCHED: bypass Rust circuit breaker
        return fallbackImplementation();
    }'''
)
# mapKeyDirectories
content = content.replace(
    '''        if (!BlueprintAnalyzer || typeof BlueprintAnalyzer.mapKeyDirectories !== 'function') {
            return fallbackImplementation();
        }
        // Use CircuitBreaker to try Rust first, fall back to TypeScript
        return this.rustCircuitBreaker.execute(rustImplementation, fallbackImplementation);
    }''',
    '''        // PATCHED: bypass Rust circuit breaker
        return fallbackImplementation();
    }'''
)
with open('$SE', 'w') as f:
    f.write(content)
"
echo "  [OK] semantic-engine.js: bypassed Rust circuit breakers"

echo ""
echo "Done! Next steps:"
echo "  1. pkill -f 'in-memoria server'"
echo "  2. Use learn_codebase_intelligence(force=true) via MCP"

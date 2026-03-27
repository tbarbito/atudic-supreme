#!/usr/bin/env python3
"""
Minifica e concatena assets JS e CSS do frontend AtuDIC.

Uso:
    python scripts/minify_assets.py

Gera:
    static/js/app.min.js    — módulos essenciais concatenados e minificados (boot)
    static/js/integration-*.min.js — módulos lazy minificados individualmente
    static/css/app.min.css  — theme.css + app-inline.css minificados

Nota: Os módulos essenciais são carregados no boot (index.html).
      Os módulos lazy são carregados sob demanda pelo router (loadModule).
"""
import os
import sys

# Força UTF-8 no Windows para evitar UnicodeEncodeError ao imprimir emojis
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Adicionar raiz do projeto ao path para imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

try:
    import rjsmin
    import rcssmin
except ImportError:
    print("❌ Pacotes rjsmin e rcssmin são necessários.")
    print("   pip install rjsmin rcssmin")
    sys.exit(1)


# Módulos essenciais (carregados no boot via index.html)
JS_ESSENTIAL = [
    "static/js/api-client.js",
    "static/js/integration-core.js",
    "static/js/integration-auth.js",
    "static/js/integration-environments.js",
]

# Módulos lazy (carregados sob demanda pelo router)
JS_LAZY = [
    "static/js/integration-commands.js",
    "static/js/integration-pipelines.js",
    "static/js/integration-ci-cd.js",
    "static/js/integration-schedules.js",
    "static/js/integration-repositories.js",
    "static/js/integration-source-control.js",
    "static/js/integration-ui.js",
]

CSS_FILES = [
    "theme.css",
    "static/css/app-inline.css",
]

# Outputs
JS_OUTPUT = "static/js/app.min.js"
CSS_OUTPUT = "static/css/app.min.css"


def minify_js_bundle(project_root):
    """Concatena e minifica módulos essenciais em app.min.js."""
    combined = []
    total_original = 0

    for js_file in JS_ESSENTIAL:
        filepath = os.path.join(project_root, js_file)
        if not os.path.exists(filepath):
            print(f"  ⚠️ Arquivo não encontrado: {js_file}")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        total_original += len(content.encode("utf-8"))
        combined.append(f"/* === {os.path.basename(js_file)} === */")
        combined.append(content)

    full_js = "\n;\n".join(combined)
    minified = rjsmin.jsmin(full_js)

    output_path = os.path.join(project_root, JS_OUTPUT)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(minified)

    minified_size = len(minified.encode("utf-8"))
    reduction = (1 - minified_size / total_original) * 100 if total_original else 0
    print(f"  ✅ JS essencial: {total_original / 1024:.0f}KB → {minified_size / 1024:.0f}KB ({reduction:.0f}% redução)")
    return output_path


def minify_js_lazy(project_root):
    """Minifica cada módulo lazy individualmente (para carregamento sob demanda)."""
    total_original = 0
    total_minified = 0
    outputs = []

    for js_file in JS_LAZY:
        filepath = os.path.join(project_root, js_file)
        if not os.path.exists(filepath):
            print(f"  ⚠️ Arquivo não encontrado: {js_file}")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        original_size = len(content.encode("utf-8"))
        total_original += original_size

        minified = rjsmin.jsmin(content)
        minified_size = len(minified.encode("utf-8"))
        total_minified += minified_size

        # Gera integration-commands.min.js etc.
        basename = os.path.basename(js_file).replace(".js", ".min.js")
        output_path = os.path.join(project_root, "static/js", basename)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(minified)

        outputs.append(output_path)

    if total_original:
        reduction = (1 - total_minified / total_original) * 100
        print(f"  ✅ JS lazy ({len(outputs)} módulos): {total_original / 1024:.0f}KB → {total_minified / 1024:.0f}KB ({reduction:.0f}% redução)")
    return outputs


def minify_css(project_root):
    """Concatena e minifica todos os CSS."""
    combined = []
    total_original = 0

    for css_file in CSS_FILES:
        filepath = os.path.join(project_root, css_file)
        if not os.path.exists(filepath):
            print(f"  ⚠️ Arquivo não encontrado: {css_file}")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        total_original += len(content.encode("utf-8"))
        combined.append(content)

    full_css = "\n".join(combined)
    minified = rcssmin.cssmin(full_css)

    output_path = os.path.join(project_root, CSS_OUTPUT)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(minified)

    minified_size = len(minified.encode("utf-8"))
    reduction = (1 - minified_size / total_original) * 100 if total_original else 0
    print(f"  ✅ CSS: {total_original / 1024:.0f}KB → {minified_size / 1024:.0f}KB ({reduction:.0f}% redução)")
    return output_path


def main():
    print("🔧 Minificando assets do AtuDIC Frontend...")
    print()

    js_out = minify_js_bundle(PROJECT_ROOT)
    lazy_out = minify_js_lazy(PROJECT_ROOT)
    css_out = minify_css(PROJECT_ROOT)

    print()
    print(f"📦 Arquivos gerados:")
    print(f"   {js_out}")
    for f in lazy_out:
        print(f"   {f}")
    print(f"   {css_out}")
    print()
    print("✅ Minificação concluída!")


if __name__ == "__main__":
    main()

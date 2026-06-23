#!/bin/zsh

cd "$(dirname "$0")"

CONDA="/Users/mickaelbegon/miniconda3/bin/conda"

if [ ! -x "$CONDA" ]; then
  echo "Conda introuvable : $CONDA"
  echo "Installe Miniconda ou lance manuellement avec un Python qui contient pyserial."
  exit 1
fi

"$CONDA" run -n fleches python afficher_fleches_laptop.py

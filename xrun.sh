# Rscript -e "rmarkdown::render('notebooks/DiffInDiffAll.Rmd')"
# Rscript -e "rmarkdown::render('notebooks/DiffInDiffTWFE.Rmd')"
# Rscript -e "rmarkdown::render('notebooks/DiffInDiffCallaway.Rmd')"
# Rscript -e "rmarkdown::render('notebooks/AnalyzeSonarQubeWarnings.Rmd')"

# Rscript -e "rmarkdown::render('notebooks/NonCausalMethods.Rmd')"

cp notebooks/DiffInDiffPosterFigures.Rmd notebooks/DiffInDiffPosterFigures.Rmd.bak

python - <<'PY'
from pathlib import Path
import re

p = Path("notebooks/DiffInDiffPosterFigures.Rmd")
s = p.read_text()

# Remove unsupported alpha argument from ggplot2::element_line(...)
# This preserves the same plot structure; only line transparency is removed.
s2 = re.sub(r",\s*alpha\s*=\s*[0-9.]+", "", s)
s2 = re.sub(r"alpha\s*=\s*[0-9.]+\s*,\s*", "", s2)

p.write_text(s2)

print("Patched unsupported alpha argument in element_line/theme calls.")
PY

Rscript -e "rmarkdown::render('notebooks/DiffInDiffPosterFigures.Rmd')"


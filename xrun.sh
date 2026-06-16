# cp notebooks/DiffInDiffAll.Rmd notebooks/DiffInDiffAll.Rmd.bak

# python - <<'PY'
# from pathlib import Path

# p = Path("notebooks/DiffInDiffAll.Rmd")
# s = p.read_text()

# old = '''dynamic_plot <- ggplot(dynamic_effects, aes(x = time, y = estimate, color = method, group = method)) +
#     # Error bars with linetype mapped to significance
#     geom_errorbar(aes(ymin = conf.low, ymax = conf.high, linetype = linetype_sig),
#                   position = pos, width = 0.4) +
#     # Points with shape mapped to significance
#     geom_point(aes(shape = significant, fill = after_scale(ifelse(significant, color, NA))),
#                position = pos, size = 1.5) +
#     scale_shape_manual(values = c("TRUE" = 19, "FALSE" = 21), guide = "none") +
#     scale_linetype_identity() +
# '''

# new = '''dynamic_plot <- ggplot(dynamic_effects, aes(x = time, y = estimate, color = method, group = method)) +
#     # Error bars: draw significant and non-significant intervals as separate layers
#     geom_errorbar(data = subset(dynamic_effects, significant),
#                   aes(ymin = conf.low, ymax = conf.high),
#                   position = pos, width = 0.4, linetype = "solid") +
#     geom_errorbar(data = subset(dynamic_effects, !significant),
#                   aes(ymin = conf.low, ymax = conf.high),
#                   position = pos, width = 0.4, linetype = "dotted") +
#     # Points: filled for significant, hollow for non-significant
#     geom_point(aes(shape = significant),
#                position = pos, size = 1.5) +
#     scale_shape_manual(values = c("TRUE" = 19, "FALSE" = 1), guide = "none") +
# '''

# if old not in s:
#     raise SystemExit("Target block not found. Please inspect lines around dynamic_plot.")

# p.write_text(s.replace(old, new))
# print("Patched notebooks/DiffInDiffAll.Rmd")
# PY


Rscript -e "rmarkdown::render('notebooks/DiffInDiffAll.Rmd')"
# Rscript -e "rmarkdown::render('notebooks/DiffInDiffTWFE.Rmd')"
# Rscript -e "rmarkdown::render('notebooks/DiffInDiffCallaway.Rmd')"

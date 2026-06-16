mkdir -p .vscode

cat > .vscode/settings.json <<'EOF'
{
  "r.rpath.linux": "/home/user1-system12/miniconda3/envs/aicomplexity/bin/R",
  "r.rterm.linux": "/home/user1-system12/miniconda3/envs/aicomplexity/bin/R",
  "r.bracketedPaste": true
}
EOF


// Data-driven native TikZ authoring, not a new numerical experiment.
// Input: inspected visual-data.json, exact checked run/result pins in that object.
function draw(d) {
 const labels=["Initial sources","Change Group 00","Add Group 02","Remove Group 01"];
 const witnesses=["4 records at (0,0)","4 to 3 records at (0,0)","+1 record at (0,1)","-1 record at (0,1)"];
 let s="\\begin{tikzpicture}[font=\\sffamily\\small,>=stealth]\n";
 s+="\\node[font=\\sffamily\\bfseries\\large] at (6.2,7) {Source edits update conditional recall};\n";
 s+="\\node[align=center] at (6.2,6.35) {Weighted record groups with binary fields $A$ then $B$};\n";
 const boxes=[["Source document","Change, add or remove an assertion"],["Located witness","Retract old contribution, add new"],["Conditional counts","Copy affected prefix paths"],["Recovered answer","Evaluate $P(B=0\\mid A=0)$"]];
 boxes.forEach((b,i)=>{s+="\\node[draw,rounded corners,fill=blue!5,text width=2.8cm,minimum height=1.3cm,align=center] (b"+i+") at ("+(i*4.1)+",4.9) {\\textbf{"+b[0]+"}\\\\[3pt]"+b[1]+"};\n";if(i)s+="\\draw[->,thick] (b"+(i-1)+") -- (b"+i+");\n";});
 s+="\\node[anchor=west,font=\\bfseries] at (-1.45,3.45) {Source operation};\n";
 s+="\\node[font=\\bfseries] at (4.1,3.45) {Located contribution};\n";
 s+="\\node[font=\\bfseries] at (8.3,3.45) {Counts within $A=0$};\n";
 s+="\\node[font=\\bfseries] at (12.3,3.45) {Conditional recall};\n";
 d.rows.forEach((r,i)=>{const y=2.65-i*.9;
 s+="\\node[anchor=west] at (-1.45,"+y+") {"+labels[i]+"};\n";
 s+="\\node at (4.1,"+y+") {"+witnesses[i]+"};\n";
 s+="\\node at (8.3,"+y+") {$("+r.numerator+","+r.B1_count_given_A0+")$};\n";
 s+="\\node[draw,rounded corners,fill=green!8,minimum width=1.6cm,minimum height=.55cm] at (12.3,"+y+") {$\\displaystyle\\frac{"+r.numerator+"}{"+r.denominator+"}$};\n";});
 s+="\\node[align=center,text width=15cm] at (6.2,-1.25) {Counts are $(n(A=0,B=0),\\,n(A=0,B=1))$. Each contribution retains its exact source span.\\\\[4pt] All 16 fixed queries agree with fresh reconstruction and direct row counts.\\\\[4pt] Removing all $A=0$ support makes conditional recall undefined.};\n";
 return s+"\\end{tikzpicture}\n";
}

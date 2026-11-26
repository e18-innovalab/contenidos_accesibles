export interface DocumentReplacement {
  originalText: string;
  replacementText: string;
}

interface TextMatch {
  start: number;
  end: number;
}

function normalizeForSearch(value: string): { text: string; positions: number[] } {
  let text = '';
  const positions: number[] = [];

  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if (/\s/.test(character)) {
      if (text.length > 0 && text[text.length - 1] !== ' ') {
        text += ' ';
        positions.push(index);
      }
      continue;
    }

    const normalizedCharacter = character.toLocaleLowerCase('es');
    for (
      let normalizedIndex = 0;
      normalizedIndex < normalizedCharacter.length;
      normalizedIndex += 1
    ) {
      text += normalizedCharacter[normalizedIndex];
      positions.push(index);
    }
  }

  if (text.endsWith(' ')) {
    text = text.slice(0, -1);
    positions.pop();
  }

  return { text, positions };
}

function findTextMatch(
  source: string,
  fragment: string,
  usedMatches: TextMatch[],
): TextMatch | null {
  const normalizedSource = normalizeForSearch(source);
  const normalizedFragment = normalizeForSearch(fragment).text;
  if (!normalizedFragment) return null;

  let searchFrom = 0;
  while (searchFrom < normalizedSource.text.length) {
    const matchIndex = normalizedSource.text.indexOf(normalizedFragment, searchFrom);
    if (matchIndex < 0) return null;

    const start = normalizedSource.positions[matchIndex];
    const end =
      normalizedSource.positions[matchIndex + normalizedFragment.length - 1] + 1;
    const overlaps = usedMatches.some(
      (match) => start < match.end && end > match.start,
    );
    if (!overlaps) return { start, end };

    searchFrom = matchIndex + normalizedFragment.length;
  }

  return null;
}

export function applyDocumentReplacements(
  source: string,
  replacements: DocumentReplacement[],
): { text: string; appliedCount: number; unmatchedCount: number } {
  const usedMatches: TextMatch[] = [];
  const matches: Array<TextMatch & { replacementText: string }> = [];
  let unmatchedCount = 0;

  for (const replacement of replacements) {
    if (
      !replacement.originalText.trim() ||
      replacement.originalText.trim() === replacement.replacementText.trim()
    ) {
      continue;
    }

    const match = findTextMatch(source, replacement.originalText, usedMatches);
    if (!match) {
      unmatchedCount += 1;
      continue;
    }

    usedMatches.push(match);
    matches.push({ ...match, replacementText: replacement.replacementText });
  }

  let text = source;
  for (const match of matches.sort((a, b) => b.start - a.start)) {
    text = `${text.slice(0, match.start)}${match.replacementText}${text.slice(match.end)}`;
  }

  return { text, appliedCount: matches.length, unmatchedCount };
}

function paginateText(text: string, charsPerPage = 1100): string[] {
  const paragraphs = text.trim().split(/\n\s*\n/).filter(Boolean);
  if (paragraphs.length === 0) return [];

  const pages: string[] = [];
  let current = '';

  for (const paragraph of paragraphs) {
    const chunks: string[] = [];
    for (let offset = 0; offset < paragraph.length; offset += charsPerPage) {
      chunks.push(paragraph.slice(offset, offset + charsPerPage));
    }

    for (const chunk of chunks) {
      const candidate = current ? `${current}\n\n${chunk}` : chunk;
      if (candidate.length > charsPerPage && current) {
        pages.push(current);
        current = chunk;
      } else {
        current = candidate;
      }
    }
  }

  if (current) pages.push(current);
  return pages;
}

async function extractPdfText(file: File): Promise<string> {
  const pdfjs = await import('pdfjs-dist');
  const workerModule = await import('pdfjs-dist/build/pdf.worker.min.mjs?url');
  pdfjs.GlobalWorkerOptions.workerSrc = workerModule.default;

  const loadingTask = pdfjs.getDocument({ data: await file.arrayBuffer() });
  const pdf = await loadingTask.promise;

  try {
    const pages: string[] = [];
    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
      const page = await pdf.getPage(pageNumber);
      const content = await page.getTextContent();
      const pageText = content.items
        .filter((item) => 'str' in item)
        .map((item) => {
          if (!('str' in item)) return '';
          return `${item.str}${item.hasEOL ? '\n' : ' '}`;
        })
        .join('')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/[ \t]{2,}/g, ' ')
        .trim();
      if (pageText) pages.push(pageText);
    }
    return pages.join('\n\n');
  } finally {
    await pdf.destroy();
  }
}

async function extractDocxText(file: File): Promise<string> {
  const mammoth = await import('mammoth');
  const result = await mammoth.default.extractRawText({
    arrayBuffer: await file.arrayBuffer(),
  });
  return result.value;
}

async function extractPptxText(file: File): Promise<string> {
  const JSZip = (await import('jszip')).default;
  const zip = await JSZip.loadAsync(file);
  const slideFiles = Object.keys(zip.files)
    .filter((path) => /^ppt\/slides\/slide\d+\.xml$/.test(path))
    .sort((a, b) => {
      const pageA = Number(a.match(/slide(\d+)\.xml$/)?.[1] ?? 0);
      const pageB = Number(b.match(/slide(\d+)\.xml$/)?.[1] ?? 0);
      return pageA - pageB;
    });

  const slides: string[] = [];
  for (const path of slideFiles) {
    const fileEntry = zip.file(path);
    if (!fileEntry) continue;

    const xml = new DOMParser().parseFromString(
      await fileEntry.async('text'),
      'application/xml',
    );
    if (xml.querySelector('parsererror')) {
      throw new Error('No se pudo leer el texto de una diapositiva.');
    }

    const paragraphs = Array.from(
      xml.getElementsByTagNameNS(
        'http://schemas.openxmlformats.org/drawingml/2006/main',
        'p',
      ),
    )
      .map((paragraph) =>
        Array.from(
          paragraph.getElementsByTagNameNS(
            'http://schemas.openxmlformats.org/drawingml/2006/main',
            't',
          ),
        )
          .map((textNode) => textNode.textContent ?? '')
          .join(''),
      )
      .filter(Boolean);

    slides.push(paragraphs.join('\n'));
  }

  return slides.join('\n\n');
}

export async function extractDocumentText(file: File): Promise<string> {
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  if (extension === '.pdf') return extractPdfText(file);
  if (extension === '.docx') return extractDocxText(file);
  if (extension === '.pptx') return extractPptxText(file);
  throw new Error('El formato del archivo no permite generar la vista previa.');
}

export function paginateDocumentText(text: string): string[] {
  return paginateText(text);
}

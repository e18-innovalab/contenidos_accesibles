declare module 'mammoth' {
  interface ExtractionResult {
    value: string;
    messages: Array<{ type: string; message: string }>;
  }

  const mammoth: {
    extractRawText(input: { arrayBuffer: ArrayBuffer }): Promise<ExtractionResult>;
  };

  export default mammoth;
}

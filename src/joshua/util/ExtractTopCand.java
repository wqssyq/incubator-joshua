/* This file is part of the Joshua Machine Translation System.
 * 
 * Joshua is free software; you can redistribute it and/or modify
 * it under the terms of the GNU Lesser General Public License as
 * published by the Free Software Foundation; either version 2.1
 * of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this library; if not, write to the Free
 * Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
 * MA 02111-1307 USA
 */

package joshua.util;

import joshua.util.io.LineReader;
import joshua.util.io.IndexedReader;

import java.io.BufferedWriter;
import java.io.OutputStreamWriter;
import java.io.FileOutputStream;
import java.io.IOException;


/**
 * This program extracts the 1-best output translations from the
 * n-best output translations generated by
 * {@link joshua.decoder.JoshuaDecoder}.
 *
 * @author wren ng thornton <wren@users.sourceforge.net>
 * @version $LastChangedDate: 2009-03-26 15:06:57 -0400 (Thu, 26 Mar 2009) $
 */
/* TODO: This class should be renamed, something like ExtractBestCandidates
 * or ExtractBestTranslations. Saying "top" implies more than one
 * (the top how many?) and "cand" is unnecessary abbreviation (also,
 * who cares about candidacy?). Once we rename this, the
 * ./example2/decode_example2.sh script will need updating (as will
 * the end-to-end code)
 */
public class ExtractTopCand {
	
	/**
	 * Usage: <code>java ExtractTopCand nbestInputFile 1bestOutputFile</code>.
	 * <p>
	 * If the input file name is "-" then input is read from
	 * <code>System.in</code>. If the output file name is "-"
	 * then output is directed to <code>System.out</code>. If
	 * a file already exists with the output file name, it is
	 * truncated before writing. The bulk of this program is
	 * implemented by
	 * {@link #extractOneBest(IndexedReader,BufferedWriter)}.
	 */
	public static void main(String[] args) {
		String inFile = "-";
		String outFile = "-";
		if (args.length == 1) {
			inFile = args[0];
		} else if (args.length == 2) {
			inFile = args[0];
			outFile = args[1];
		} else {
			System.err.println("Usage: ExtractTopCand [nbestInputFile [1bestOutputFile]]\n       (default to stdin/stdout)");
			System.exit(1);
		}
		
		try {
			// TODO: see documentation for extractOneBest
			// regarding using an n-best SegmentFileParser.
			IndexedReader<String> nbestReader =
				new IndexedReader<String>("line",
							  "-".equals(inFile)
							  ? new LineReader(System.in)
							  : new LineReader(inFile));
			
			/* TODO: This duplicates FileUtility.getWriteFileStream
			 * but with the addition of defaulting to System.out;
			 * should fix that (without breaking other clients
			 * of that method). We ultimately want something which
			 * autochecks for errors (like Writer); has a newLine
			 * method (like BufferedWriter); can wrap System.out;
			 * can autoflush; and it'd be handy to have the
			 * print/println methods of PrintStream/PrintWriter
			 * to boot. PrintWriter *almost* gives us all this,
			 * but it swallows errors and gives no way to
			 * retrieve them >:(
			 */
			BufferedWriter onebestWriter =
				new BufferedWriter(
					new OutputStreamWriter(
							   ("-".equals(outFile)
								? System.out
								: new FileOutputStream(outFile, false)
						), "UTF-8"));
			
			extractOneBest(nbestReader, onebestWriter);
			
		} catch (IOException ioe) {
			// NOTE: if our onebest was System.out, then that
			// will already have been closed by the finally
			// block. Printing to a closed PrintStream generates
			// no exceptions. We should be printing to System.err
			// anyways, but this something subtle to be aware of.
			System.err.println("There was an error: " + ioe.getMessage());
		}
	}
	
	
	/**
	 * Prints the one-best translation for each segment ID from
	 * the reader as a line on the writer, and closes both
	 * before exiting. The translations for a segment are printed
	 * in the order of the first occurance of the segment ID.
	 * Any information about the segment other than the translation
	 * (including segment ID) is not printed to the writer.
	 * 
	 * <h4>Developer Notes</h4>
	 * This implementation assumes:
	 * <ol>
	 * <li>all translations for a segment are contiguous</li>
	 * <li>the 1-best translation is the first one encountered.</li>
	 * </ol>
	 * We will need to alter the implementation if these
	 * assumptions no longer hold for the output of JoshuaDecoder
	 * (or any sensible n-best format passed to this method).
	 * <p>
	 * We should switch to using an n-best
	 * {@link joshua.decoder.segment_file.SegmentFileParser}
	 * to ensure future compatibility with being able to configure
	 * the output format of the decoder. The MERT code needs
	 * such a SegmentFileParser anyways, so that will reduce
	 * the code duplication between these two classes.
	 */
	protected static void extractOneBest(
		IndexedReader<String> nbestReader, BufferedWriter onebestWriter)
	throws IOException {
		
		try {
			String prevID = null;
			for (String line : nbestReader) {
				
				String[] columns = Regex.threeBarsWithSpace.split(line);
				
				// We allow non-integer segment IDs because the
				// Segment interface does, and we have no reason
				// to add new restrictions.
				String newID = columns[0].trim();
				
				// We want to give the same error message
				// regardless of whether there's a leading space
				// or not. And, we don't want to accidentally
				// accept lines with lots and lots of columns.
				if ("".equals(newID) || newID.startsWith("|||")) {
					throw nbestReader.wrapIOException(
						new IOException("Malformed line, missing segment ID:\n" + line));
				}
				
				// Make sure there's a translation there too
				// TODO: good error message for when the second
				// "|||" doesn't have a following field, m/\|{3}\s*$/
				if (3 > columns.length) {
					throw nbestReader.wrapIOException(
						new IOException("Malformed line, should have at least two \" ||| \":\n" + line));
				}
				
				
				if (null == prevID || ! prevID.equals(newID)) {
					onebestWriter.write(columns[1], 0, columns[1].length());
					onebestWriter.newLine();
					onebestWriter.flush();
					
					prevID = newID;
				}
			}
		} finally {
			try {
				nbestReader.close();
			} finally {
				onebestWriter.close();
			}
		}
	}
}

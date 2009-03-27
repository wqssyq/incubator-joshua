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
package joshua.decoder.hypergraph;

import java.util.ArrayList;

import joshua.decoder.ff.tm.Rule;

/**
* @author Zhifei Li, <zhifei.work@gmail.com>
* @version $LastChangedDate$
*/

public class WithModelCostsHyperEdge extends HyperEdge {
	public double[] model_costs;//store the list of models costs

	public WithModelCostsHyperEdge(Rule rl, double total_cost, Double trans_cost, ArrayList<HGNode> ant_items, double[] model_costs_) {
		super(rl, total_cost, trans_cost, ant_items);
		this.model_costs = model_costs_;
	}

}

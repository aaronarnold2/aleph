import _ from 'lodash';
import React, { PureComponent } from 'react';
import { compose } from 'redux';
import { connect } from 'react-redux';
import { FormattedMessage, injectIntl } from 'react-intl';

import { Country, Facet, Numeric, Schema, Statistics } from 'components/common';
import { selectModel } from 'selectors';
import getStatLink from 'util/getStatLink';

import './CollectionStatistics.scss';


class CollectionStatistics extends PureComponent {
  constructor(props) {
    super(props);
    this.filterValues = this.filterValues.bind(this);
    this.getLabel = this.getLabel.bind(this);
  }

  filterValues(count, value) {
    const { field, model } = this.props;
    if (field === 'schema') {
      const schema = model.getSchema(value);
      return schema.isThing();
    }
    return true;
  }

  getLabel(name) {
    const { field } = this.props;

    if (field === 'schema') {
      return <Schema.Label schema={name} plural icon />;
    } else if (field === 'countries') {
      return <Country.Name code={name} />;
    } else {
      return name;
    }
  }

  render() {
    const { collection, field, total, values } = this.props;
    const filteredValues = _.pickBy(values, this.filterValues);
    const filteredTotal = field === 'schema' ? Object.keys(filteredValues).length : total;

    return (
      <div className="CollectionStatistics bp3-card bp3-elevation-1">
        <div className="CollectionStatistics__heading">
          <h5 className="CollectionStatistics__heading__total">
            <Numeric num={filteredTotal} abbr={3} />
          </h5>
          <h5 className="CollectionStatistics__heading__label">
            <Facet.Label field={field} count={filteredTotal} />
          </h5>
        </div>
        <Statistics
          seeMoreButtonText={() => (
            <FormattedMessage
              id="collection.statistics.showmore"
              defaultMessage="Show more"
            />
          )}
          statistic={filteredValues}
          isPending={!values}
          itemLink={name => getStatLink(collection, field, name)}
          itemLabel={this.getLabel}
          ItemContentContainer={this.renderItem}
          styleType="dark"
        />
      </div>
    );
  }
}

const mapStateToProps = (state, ownProps) => {
  return { model: selectModel(state) };
};

export default compose(
  injectIntl,
  connect(mapStateToProps),
)(CollectionStatistics);
